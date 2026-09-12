import {
  BufferAttribute,
  BufferGeometry,
  Float16BufferAttribute,
  Float32BufferAttribute,
  InterleavedBufferAttribute,
  Material,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Object3D,
  ObjectSpaceNormalMap,
  StaticDrawUsage,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { Group } from "three";

type StaticMesh = Mesh<
  BufferGeometry,
  MeshBasicMaterial | MeshStandardMaterial
>;
type PreparedBatch = { mesh: StaticMesh; sources: Array<StaticMesh> };

const attributeSizes: Partial<Record<string, ReadonlyArray<number>>> = {
  position: [3],
  normal: [3],
  tangent: [4],
  uv: [2],
  uv1: [2],
  uv2: [2],
  uv3: [2],
  color: [3, 4],
};

function isStaticMesh(
  object: Object3D,
  dynamicMaterials: Set<Material>,
): object is StaticMesh {
  if (
    !(object instanceof Mesh) ||
    object.constructor !== Mesh ||
    object.children.length
  )
    return false;
  const { geometry, material } = object;
  if (
    Array.isArray(material) ||
    (material.constructor !== MeshBasicMaterial &&
      material.constructor !== MeshStandardMaterial &&
      material.constructor !== MeshPhysicalMaterial) ||
    (material instanceof MeshPhysicalMaterial && material.transmission > 0) ||
    (material instanceof MeshStandardMaterial &&
      (material.displacementMap ||
        (material.normalMap &&
          material.normalMapType === ObjectSpaceNormalMap))) ||
    !material.visible ||
    material.transparent ||
    dynamicMaterials.has(material) ||
    material.onBeforeCompile !== Material.prototype.onBeforeCompile ||
    material.customProgramCacheKey !==
      Material.prototype.customProgramCacheKey ||
    material.onBeforeRender !== Material.prototype.onBeforeRender ||
    object.onBeforeRender !== Object3D.prototype.onBeforeRender ||
    object.onAfterRender !== Object3D.prototype.onAfterRender ||
    object.onBeforeShadow !== Object3D.prototype.onBeforeShadow ||
    object.onAfterShadow !== Object3D.prototype.onAfterShadow ||
    object.customDepthMaterial ||
    object.customDistanceMaterial ||
    object.raycast !== Mesh.prototype.raycast ||
    geometry.groups.length ||
    Object.keys(geometry.morphAttributes).length ||
    geometry.drawRange.start !== 0 ||
    geometry.drawRange.count !== Infinity ||
    !geometry.attributes.position
  )
    return false;

  // The GLB uses normalized, interleaved integers. Decode supported attributes
  // before baking transforms; writing back into those integers would lose detail.
  return Object.entries(geometry.attributes).every(
    ([name, attribute]) =>
      (attribute instanceof BufferAttribute ||
        attribute instanceof InterleavedBufferAttribute) &&
      !(attribute instanceof Float16BufferAttribute) &&
      (attribute instanceof InterleavedBufferAttribute
        ? attribute.data.usage
        : attribute.usage) === StaticDrawUsage &&
      attributeSizes[name]?.includes(attribute.itemSize),
  );
}

function batchKey(mesh: StaticMesh): string {
  const attributes = Object.entries(mesh.geometry.attributes)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, attribute]) => [
      name,
      attribute.itemSize,
      attribute.normalized,
      attribute.array.constructor.name,
    ]);
  return JSON.stringify([
    mesh.material.uuid,
    !!mesh.geometry.index,
    attributes,
    mesh.castShadow,
    mesh.receiveShadow,
    mesh.layers.mask,
    mesh.renderOrder,
    mesh.frustumCulled,
  ]);
}

// Restore the utility's nullable runtime contract at this seam.
function mergeStaticParts(parts: Array<BufferGeometry>): BufferGeometry | null {
  return mergeGeometries(parts, false);
}

/** Run after every scene installer. The caller owns source and merged resources. */
export function batchStaticScene(
  scene: Group,
  dynamicObjects: ReadonlySet<Object3D>,
): void {
  scene.updateWorldMatrix(true, true);
  const rootDeterminant = scene.matrixWorld.determinant();
  if (!Number.isFinite(rootDeterminant) || rootDeterminant <= 0) return;
  const rootInverse = scene.matrixWorld.clone().invert();
  const dynamicMeshes = new Set<Object3D>();
  const dynamicMaterials = new Set<Material>();
  for (const object of dynamicObjects) {
    object.traverse((descendant) => {
      dynamicMeshes.add(descendant);
      if (!(descendant instanceof Mesh)) return;
      const materials = Array.isArray(descendant.material)
        ? descendant.material
        : [descendant.material];
      for (const material of materials) dynamicMaterials.add(material);
    });
  }

  const buckets = new Map<string, Array<StaticMesh>>();
  const transform = new Matrix4();
  scene.traverseVisible((object) => {
    if (dynamicMeshes.has(object) || !isStaticMesh(object, dynamicMaterials))
      return;
    // Flattening a non-default ancestor group order would change render ordering.
    for (let parent = object.parent; parent; parent = parent.parent) {
      if (parent.renderOrder !== 0) return;
      if (parent === scene) break;
    }
    transform.multiplyMatrices(rootInverse, object.matrixWorld);
    const determinant = transform.determinant();
    if (!Number.isFinite(determinant) || determinant <= 0) return;
    const key = batchKey(object);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(object);
    else buckets.set(key, [object]);
  });

  const prepared: Array<PreparedBatch> = [];
  try {
    for (const sources of buckets.values()) {
      if (sources.length < 2) continue;
      const parts: Array<BufferGeometry> = [];
      let merged: BufferGeometry | null = null;
      try {
        for (const source of sources) {
          const part = new BufferGeometry();
          parts.push(part);
          part.setIndex(source.geometry.index?.clone() ?? null);
          for (const [name, attribute] of Object.entries(
            source.geometry.attributes,
          )) {
            const values = new Float32Array(
              attribute.count * attribute.itemSize,
            );
            for (let vertex = 0; vertex < attribute.count; vertex++) {
              for (
                let component = 0;
                component < attribute.itemSize;
                component++
              ) {
                values[vertex * attribute.itemSize + component] =
                  attribute.getComponent(vertex, component);
              }
            }
            part.setAttribute(
              name,
              new Float32BufferAttribute(values, attribute.itemSize),
            );
          }
          transform.multiplyMatrices(rootInverse, source.matrixWorld);
          part.applyMatrix4(transform);
        }
        merged = mergeStaticParts(parts);
        if (!merged) continue;
        merged.computeBoundingBox();
        merged.computeBoundingSphere();
        const first = sources[0];
        const mesh = new Mesh(merged, first.material);
        mesh.name = `Static batch: ${first.material.name || first.material.type}`;
        mesh.castShadow = first.castShadow;
        mesh.receiveShadow = first.receiveShadow;
        mesh.layers.mask = first.layers.mask;
        mesh.renderOrder = first.renderOrder;
        mesh.frustumCulled = first.frustumCulled;
        prepared.push({ mesh, sources });
        merged = null;
      } finally {
        parts.forEach((part) => part.dispose());
        merged?.dispose();
      }
    }
  } catch (error) {
    prepared.forEach(({ mesh }) => mesh.geometry.dispose());
    throw error;
  }

  // All geometry is prepared first, so a failed preparation leaves the scene intact.
  for (const { mesh, sources } of prepared) {
    scene.add(mesh);
    sources.forEach((source) => source.removeFromParent());
  }
}
