import { Box3, Group, Mesh, MeshStandardMaterial, Vector3 } from "three";
import { studyTaskLight } from "./roomLayout";

type Axis = "x" | "y" | "z";

function rodGeometry(mesh: Mesh) {
  mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox!;
  const size = bounds.getSize(new Vector3());
  const axes: Array<Axis> = ["x", "y", "z"];
  const axis = axes.reduce((longest, next) =>
    size[next] > size[longest] ? next : longest,
  );
  return { bounds, size, axis, center: bounds.getCenter(new Vector3()) };
}

function positionRod(mesh: Mesh, start: Vector3, end: Vector3) {
  const { size, axis, center } = rodGeometry(mesh);
  const direction = end.clone().sub(start);
  const localAxis = new Vector3();
  localAxis[axis] = 1;
  // Preserve the brass arm's thickness; only its length and direction change.
  mesh.scale[axis] = direction.length() / size[axis];
  mesh.quaternion.setFromUnitVectors(localAxis, direction.normalize());
  mesh.position.copy(start).add(end).multiplyScalar(0.5);
  mesh.position.sub(
    center.multiply(mesh.scale).applyQuaternion(mesh.quaternion),
  );
}

export function positionStudyTaskLamp(scene: Group) {
  const base = scene.getObjectByName("Task_lamp__base");
  const lower = scene.getObjectByName("Task_lamp__lower_arm");
  const upper = scene.getObjectByName("Task_lamp__upper_arm");
  const shade = scene.getObjectByName("Task_lamp__enamel_shade");
  const lens = scene.getObjectByName("Task_lamp__lit_lens");
  if (
    !(base instanceof Mesh) ||
    !(lower instanceof Mesh) ||
    !(upper instanceof Mesh) ||
    !(shade instanceof Mesh) ||
    !(lens instanceof Mesh)
  )
    throw new Error("The study task lamp is missing a required component.");

  scene.updateMatrixWorld(true);
  const oldLens = new Box3().setFromObject(lens).getCenter(new Vector3());
  const shadeCenter = new Box3().setFromObject(shade).getCenter(new Vector3());
  const { bounds, axis, center } = rodGeometry(upper);
  const ends = [bounds.min[axis], bounds.max[axis]].map((coordinate) => {
    const endpoint = center.clone();
    endpoint[axis] = coordinate;
    return endpoint.applyMatrix4(upper.matrixWorld);
  });
  const attachment =
    ends[0].distanceToSquared(shadeCenter) <
    ends[1].distanceToSquared(shadeCenter)
      ? ends[0]
      : ends[1];
  attachment.sub(oldLens);

  const source = new Vector3(...studyTaskLight.position);
  const direction = new Vector3(...studyTaskLight.target)
    .sub(source)
    .normalize();
  const head = new Group();
  head.name = "Study task lamp adjustable head";
  head.position.copy(oldLens);
  scene.add(head);
  head.updateMatrixWorld(true);
  head.attach(shade);
  head.attach(lens);
  head.quaternion.setFromUnitVectors(new Vector3(0, -1, 0), direction);
  // Keep the light just outside the lens so its housing cannot block the beam.
  head.position.copy(source).addScaledVector(direction, -0.018);

  const baseBounds = new Box3().setFromObject(base);
  const foot = baseBounds.getCenter(new Vector3());
  foot.y = baseBounds.max.y - 0.004;
  const elbow = new Vector3(foot.x - 0.03, 1.69, 0.3);
  const hinge = attachment.applyQuaternion(head.quaternion).add(head.position);
  positionRod(lower, foot, elbow);
  positionRod(upper, elbow, hinge);

  if (lens.material instanceof MeshStandardMaterial) {
    // Other room LEDs share the source material and must retain their brightness.
    const material = lens.material.clone();
    material.emissiveIntensity *= 0.8;
    lens.material = material;
  }
  scene.updateMatrixWorld(true);
}
