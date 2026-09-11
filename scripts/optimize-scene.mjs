import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

// Optimize the untextured curiosity-house export without changing vertex precision,
// topology, node names, material names, camera data, or the editable Blender source.
const [input, output] = process.argv.slice(2);
assert(
  input && output,
  "Usage: node scripts/optimize-scene.mjs input.glb output.glb",
);
assert.notEqual(
  resolve(input),
  resolve(output),
  "Write to a separate output file first.",
);
const source = await readFile(input);
assert.equal(source.readUInt32LE(0), 0x46546c67, "Expected a GLB file.");
assert.equal(source.readUInt32LE(4), 2, "Expected glTF 2.0.");
const jsonLength = source.readUInt32LE(12);
assert.equal(source.readUInt32LE(16), 0x4e4f534a, "Expected a JSON chunk.");
assert.equal(
  source.readUInt32LE(24 + jsonLength),
  0x004e4942,
  "Expected a BIN chunk.",
);
const document = JSON.parse(source.subarray(20, 20 + jsonLength).toString());
const binary = source.subarray(28 + jsonLength);
const supportedExtensions = new Set([
  "EXT_meshopt_compression",
  "KHR_materials_emissive_strength",
  "KHR_materials_specular",
  "KHR_mesh_quantization",
]);
assert(
  (document.extensionsUsed ?? []).every((name) =>
    supportedExtensions.has(name),
  ),
  "This export uses extensions the scene optimizer does not support.",
);
assert(
  !document.animations?.length && !document.skins?.length,
  "Animated exports need a separate optimizer.",
);
assert(
  !document.textures?.length && !document.images?.length,
  "UV removal is only safe for this untextured export.",
);
assert.equal(
  document.buffers.length,
  2,
  "Expected binary and Meshopt fallback buffers.",
);
assert(
  document.buffers[1].extensions?.EXT_meshopt_compression?.fallback,
  "Expected a virtual Meshopt fallback buffer.",
);
assert(
  document.nodes.every((node) => node.mesh === undefined || node.name),
  "Mesh deduplication requires named nodes.",
);
assert(
  document.meshes.every((mesh) =>
    mesh.primitives.every((primitive) => !primitive.targets),
  ),
  "Morph targets are not supported.",
);

// Strip runtime-replaced artwork and the intentionally removed gaming subwoofer.
// Keep named nodes for stable object identities, including all screen/portrait anchors.
function isUnusedMesh(name) {
  return (
    (/^Character art \/ /.test(name) &&
      !/^Character art \/ (background|brass frame)/.test(name)) ||
    /^(Display star|Pixel star|Synthwave terrain|Tiny sunset)/.test(name) ||
    /^(Study|Studio) display \/ luminous flower diagram/.test(name) ||
    /^Pendant lamp \/ (stem|red shade)/.test(name) ||
    /^Gaming subwoofer \/ /.test(name)
  );
}
let removedMeshes = 0;
for (const node of document.nodes) {
  if (node.mesh !== undefined && isUnusedMesh(node.name)) {
    delete node.mesh;
    removedMeshes++;
  }
}
for (const mesh of document.meshes) {
  for (const primitive of mesh.primitives) {
    for (const semantic of Object.keys(primitive.attributes)) {
      if (semantic.startsWith("TEXCOORD_"))
        delete primitive.attributes[semantic];
    }
  }
}

const meshes = [];
const meshKeys = new Map();
for (const node of document.nodes) {
  if (node.mesh === undefined) continue;
  const mesh = document.meshes[node.mesh];
  // Nodes retain their authoritative object names; identical mesh payloads can share.
  const key = JSON.stringify({ ...mesh, name: undefined });
  let index = meshKeys.get(key);
  if (index === undefined) {
    index = meshes.length;
    meshes.push(mesh);
    meshKeys.set(key, index);
  }
  node.mesh = index;
}
const originalMeshCount = document.meshes.length;
document.meshes = meshes;

const usedAccessors = new Set();
for (const mesh of meshes) {
  for (const primitive of mesh.primitives) {
    Object.values(primitive.attributes).forEach((index) =>
      usedAccessors.add(index),
    );
    if (primitive.indices !== undefined) usedAccessors.add(primitive.indices);
  }
}
const accessorIndices = [...usedAccessors].sort((a, b) => a - b);
const accessorMap = new Map(
  accessorIndices.map((index, next) => [index, next]),
);
const accessors = accessorIndices.map((index) => document.accessors[index]);
assert(
  accessors.every((accessor) => !accessor.sparse),
  "Sparse accessors are not supported.",
);
for (const mesh of meshes) {
  for (const primitive of mesh.primitives) {
    for (const semantic of Object.keys(primitive.attributes)) {
      primitive.attributes[semantic] = accessorMap.get(
        primitive.attributes[semantic],
      );
    }
    if (primitive.indices !== undefined)
      primitive.indices = accessorMap.get(primitive.indices);
  }
}
document.accessors = accessors;
const viewIndices = [
  ...new Set(accessors.map((accessor) => accessor.bufferView)),
].sort((a, b) => a - b);
assert(
  viewIndices.every(Number.isInteger),
  "All accessors must reference a buffer view.",
);
const viewMap = new Map(viewIndices.map((index, next) => [index, next]));
const views = viewIndices.map((index) => document.bufferViews[index]);
accessors.forEach((accessor) => {
  accessor.bufferView = viewMap.get(accessor.bufferView);
});
document.bufferViews = views;

const align = (length) => Math.ceil(length / 4) * 4;
const chunks = [];
const payloads = new Map();
let binaryLength = 0;
let fallbackLength = 0;
for (const view of views) {
  const compressed = view.extensions?.EXT_meshopt_compression;
  const range = compressed ?? view;
  assert.equal(
    range.buffer,
    0,
    "Encoded payloads must live in the binary buffer.",
  );
  const start = range.byteOffset ?? 0;
  const end = start + range.byteLength;
  assert(end <= binary.length, "Buffer view exceeds the binary chunk.");
  const data = binary.subarray(start, end);
  const key = createHash("sha256").update(data).digest("hex");
  let offset = payloads.get(key);
  if (offset === undefined) {
    offset = binaryLength;
    payloads.set(key, offset);
    chunks.push(data, Buffer.alloc(align(data.length) - data.length));
    binaryLength += align(data.length);
  }
  range.byteOffset = offset;
  if (compressed) {
    assert.equal(
      view.buffer,
      1,
      "Compressed views must use the virtual fallback.",
    );
    view.byteOffset = fallbackLength;
    fallbackLength += align(view.byteLength);
  }
}
document.buffers[0].byteLength = binaryLength;
document.buffers[1].byteLength = fallbackLength;
const json = Buffer.from(JSON.stringify(document));
const paddedJson = Buffer.alloc(align(json.length), 0x20);
json.copy(paddedJson);
const header = Buffer.alloc(20);
header.writeUInt32LE(0x46546c67, 0);
header.writeUInt32LE(2, 4);
header.writeUInt32LE(28 + paddedJson.length + binaryLength, 8);
header.writeUInt32LE(paddedJson.length, 12);
header.writeUInt32LE(0x4e4f534a, 16);
const binaryHeader = Buffer.alloc(8);
binaryHeader.writeUInt32LE(binaryLength, 0);
binaryHeader.writeUInt32LE(0x004e4942, 4);
const optimized = Buffer.concat([header, paddedJson, binaryHeader, ...chunks]);
assert(
  optimized.length < source.length,
  "No smaller output; leave the existing asset unchanged.",
);
await writeFile(output, optimized);
console.log(
  JSON.stringify(
    {
      beforeBytes: source.length,
      afterBytes: optimized.length,
      savedBytes: source.length - optimized.length,
      unusedMeshPayloadsRemoved: removedMeshes,
      meshDefinitions: [originalMeshCount, meshes.length],
      geometryPrecision: "unchanged",
    },
    null,
    2,
  ),
);
