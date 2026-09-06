// Offline artwork tool. Uses Sharp already available in the workspace toolchain.
// node scripts/trace-hero.mjs --crop /tmp/hero-proof
// node scripts/trace-hero.mjs --output src/components/hero/layers/studio.svg
// The PNG is an authoring reference only. Output contains vector contours, never images.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { gzipSync } from "node:zlib";
import sharp from "sharp";

const WIDTH = 1536;
const HEIGHT = 1024;
const PAPER = "#fbe3be";
const COLORS = 128;
const TOLERANCE = 0.5;

// Paint ownership, from back to front. Later polygons take precedence.
const REGIONS = [
  { name: "paper", polygon: [] },
  {
    name: "ground",
    polygon: [
      [0, 801],
      [1536, 678],
      [1536, 1024],
      [0, 1024],
    ],
  },
  {
    name: "building",
    polygon: [
      [290, 1000],
      [291, 837],
      [319, 816],
      [326, 602],
      [351, 585],
      [357, 440],
      [384, 421],
      [389, 266],
      [487, 247],
      [532, 226],
      [534, 165],
      [565, 165],
      [565, 226],
      [587, 231],
      [590, 260],
      [872, 195],
      [912, 196],
      [921, 247],
      [1026, 267],
      [1027, 445],
      [1076, 460],
      [1083, 632],
      [1107, 640],
      [1116, 855],
      [1133, 869],
      [1135, 932],
      [1010, 962],
      [425, 1002],
    ],
  },
  {
    name: "workspace",
    polygon: [
      [479, 733],
      [757, 700],
      [770, 888],
      [746, 920],
      [466, 939],
      [460, 771],
    ],
  },
  {
    name: "kitchen",
    polygon: [
      [770, 700],
      [1062, 670],
      [1092, 873],
      [777, 919],
    ],
  },
  {
    name: "audio",
    polygon: [
      [514, 516],
      [910, 498],
      [965, 520],
      [974, 645],
      [920, 669],
      [496, 694],
      [488, 544],
    ],
  },
  {
    name: "computer",
    polygon: [
      [590, 322],
      [854, 296],
      [951, 314],
      [971, 476],
      [901, 502],
      [575, 525],
      [581, 486],
    ],
  },
  {
    name: "observatory",
    polygon: [
      [574, 246],
      [582, 141],
      [618, 77],
      [670, 43],
      [714, 23],
      [779, 23],
      [825, 55],
      [857, 97],
      [875, 162],
      [887, 257],
      [848, 279],
      [648, 290],
      [576, 264],
    ],
  },
  {
    name: "bonsai",
    polygon: [
      [1164, 450],
      [1331, 333],
      [1436, 389],
      [1422, 599],
      [1474, 614],
      [1496, 664],
      [1490, 767],
      [1465, 810],
      [1319, 838],
      [1160, 817],
      [1131, 763],
      [1128, 643],
      [1166, 596],
      [1248, 581],
      [1232, 513],
    ],
  },
  {
    name: "blossoms",
    polygon: [
      [934, 0],
      [1536, 0],
      [1536, 603],
      [1467, 572],
      [1419, 622],
      [1332, 607],
      [1369, 554],
      [1366, 485],
      [1386, 410],
      [1338, 377],
      [1282, 388],
      [1251, 469],
      [1187, 588],
      [1130, 572],
      [1127, 507],
      [1015, 487],
      [988, 399],
      [1019, 346],
      [959, 292],
      [928, 201],
    ],
  },
];

function regionMap(width, height, offsetX, offsetY) {
  const labels = new Uint8Array(width * height);
  for (let region = 1; region < REGIONS.length; region++) {
    const points = REGIONS[region].polygon;
    for (let y = 0; y < height; y++) {
      const scanY = y + offsetY + 0.5;
      const crossings = [];
      for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
        const [ax, ay] = points[j];
        const [bx, by] = points[i];
        if (ay > scanY !== by > scanY) {
          crossings.push(ax + ((scanY - ay) * (bx - ax)) / (by - ay));
        }
      }
      crossings.sort((a, b) => a - b);
      for (let i = 0; i + 1 < crossings.length; i += 2) {
        const start = Math.max(0, Math.ceil(crossings[i] - offsetX - 0.5));
        const end = Math.min(
          width,
          Math.ceil(crossings[i + 1] - offsetX - 0.5),
        );
        if (end <= start) continue;
        labels.fill(region, y * width + start, y * width + end);
      }
    }
  }
  return labels;
}

// Douglas–Peucker contour simplification; preserve the print's narrow ink lines.
function simplify(points, tolerance) {
  if (points.length < 4) return points;
  const keep = new Uint8Array(points.length);
  keep[0] = keep[points.length - 1] = 1;
  const stack = [[0, points.length - 1]];
  while (stack.length) {
    const [first, last] = stack.pop();
    const [ax, ay] = points[first];
    const [bx, by] = points[last];
    const dx = bx - ax;
    const dy = by - ay;
    const length = dx * dx + dy * dy;
    let furthest = -1;
    let maxDistance = tolerance * tolerance;
    for (let i = first + 1; i < last; i++) {
      const [x, y] = points[i];
      const t = length
        ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / length))
        : 0;
      const distance = (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2;
      if (distance > maxDistance) {
        maxDistance = distance;
        furthest = i;
      }
    }
    if (furthest !== -1) {
      keep[furthest] = 1;
      stack.push([first, furthest], [furthest, last]);
    }
  }
  return points.filter((_, index) => keep[index]);
}

function compactPath(points, offsetX, offsetY) {
  const [startX, startY] = points[0];
  let d = `M${startX + offsetX} ${startY + offsetY}`;
  for (let i = 1; i < points.length; i++) {
    const dx = points[i][0] - points[i - 1][0];
    const dy = points[i][1] - points[i - 1][1];
    d += dx === 0 ? `v${dy}` : dy === 0 ? `h${dx}` : `l${dx} ${dy}`;
  }
  return d + "Z";
}

function pathFromEdges(edges, stride, offsetX, offsetY) {
  const paths = [];
  // Each directed edge follows one ink region clockwise. Multiple exits at a
  // diagonal contact are legal; even-odd filling preserves islands and holes.
  while (edges.size) {
    const start = edges.keys().next().value;
    let current = start;
    const points = [];
    do {
      points.push([current % stride, Math.floor(current / stride)]);
      const exits = edges.get(current);
      if (!exits?.length)
        throw new Error("Open contour in source segmentation");
      current = exits.pop();
      if (!exits.length)
        edges.delete(points.at(-1)[1] * stride + points.at(-1)[0]);
    } while (current !== start);
    // Split the closed loop at its middle before simplifying to avoid the
    // coincident-endpoint degeneracy in Douglas–Peucker.
    const middle = Math.floor(points.length / 2);
    const reduced = [
      ...simplify(points.slice(0, middle + 1), TOLERANCE).slice(0, -1),
      ...simplify([...points.slice(middle), points[0]], TOLERANCE).slice(0, -1),
    ];
    if (reduced.length < 3) continue;
    let area = 0;
    for (let i = 0; i < reduced.length; i++) {
      const next = reduced[(i + 1) % reduced.length];
      area += reduced[i][0] * next[1] - next[0] * reduced[i][1];
    }
    // Discard only isolated sub-pixel dust, not rivets, stems or screen detail.
    if (Math.abs(area) < 1) continue;
    paths.push(compactPath(reduced, offsetX, offsetY));
  }
  return paths.join("");
}

function contours(data, width, height, regions, offsetX, offsetY) {
  const palette = new Map();
  const pixels = new Int32Array(width * height).fill(-1);
  const colors = [];
  for (let i = 0; i < pixels.length; i++) {
    if (!regions[i]) continue;
    const hex =
      "#" +
      [...data.subarray(i * 3, i * 3 + 3)]
        .map((c) => c.toString(16).padStart(2, "0"))
        .join("");
    if (!palette.has(hex)) {
      palette.set(hex, colors.length);
      colors.push(hex);
    }
    pixels[i] = regions[i] * 256 + palette.get(hex);
  }
  const buckets = new Map();
  const stride = width + 1;
  function edge(label, from, to) {
    if (!buckets.has(label)) buckets.set(label, new Map());
    const bucket = buckets.get(label);
    if (!bucket.has(from)) bucket.set(from, []);
    bucket.get(from).push(to);
  }
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const label = pixels[i];
      if (label === -1) continue;
      const vertex = y * stride + x;
      if (y === 0 || pixels[i - width] !== label)
        edge(label, vertex, vertex + 1);
      if (x === width - 1 || pixels[i + 1] !== label)
        edge(label, vertex + 1, vertex + stride + 1);
      if (y === height - 1 || pixels[i + width] !== label)
        edge(label, vertex + stride + 1, vertex + stride);
      if (x === 0 || pixels[i - 1] !== label)
        edge(label, vertex + stride, vertex);
    }
  }
  const groups = REGIONS.map(() => []);
  for (const [label, edges] of buckets) {
    const d = pathFromEdges(edges, stride, offsetX, offsetY);
    if (!d) continue;
    const color = colors[label % 256];
    groups[Math.floor(label / 256)].push(
      `<path fill="${color}" stroke="${color}" stroke-width="0.35" stroke-linejoin="round" d="${d}"/>`,
    );
  }
  return groups;
}

// PNG supports only 2/4/16/256 palette entries. Merge the nearest printed
// shades ourselves to get 128 colors without falling back to a 16-color PNG.
function mergePalette(data) {
  const histogram = new Map();
  for (let i = 0; i < data.length; i += 3) {
    const key = data.readUIntBE(i, 3);
    histogram.set(key, (histogram.get(key) ?? 0) + 1);
  }
  const clusters = [...histogram].map(([key, count]) => ({
    rgb: [key >> 16, (key >> 8) & 255, key & 255],
    count,
    keys: [key],
  }));
  while (clusters.length > COLORS) {
    let closest = Infinity;
    let pair = [0, 1];
    for (let i = 0; i < clusters.length; i++) {
      for (let j = i + 1; j < clusters.length; j++) {
        const a = clusters[i];
        const b = clusters[j];
        const distance = a.rgb.reduce(
          (sum, value, c) => sum + (value - b.rgb[c]) ** 2,
          0,
        );
        if (distance < closest) {
          closest = distance;
          pair = [i, j];
        }
      }
    }
    const [i, j] = pair;
    const a = clusters[i];
    const b = clusters[j];
    const count = a.count + b.count;
    clusters[i] = {
      rgb: a.rgb.map(
        (value, c) => (value * a.count + b.rgb[c] * b.count) / count,
      ),
      count,
      keys: [...a.keys, ...b.keys],
    };
    clusters.splice(j, 1);
  }
  const lookup = new Map();
  for (const cluster of clusters)
    for (const key of cluster.keys)
      lookup.set(key, cluster.rgb.map(Math.round));
  for (let i = 0; i < data.length; i += 3) {
    const rgb = lookup.get(data.readUIntBE(i, 3));
    data[i] = rgb[0];
    data[i + 1] = rgb[1];
    data[i + 2] = rgb[2];
  }
  return data;
}

async function main() {
  const args = process.argv.slice(2);
  const cropIndex = args.indexOf("--crop");
  const cropDir = cropIndex === -1 ? null : args[cropIndex + 1];
  const outputIndex = args.indexOf("--output");
  if (!cropDir && (outputIndex === -1 || !args[outputIndex + 1])) {
    throw new Error("Provide --crop <proof-directory> or --output <svg-path>");
  }
  const crop = cropDir
    ? { left: 565, top: 20, width: 415, height: 515 }
    : { left: 0, top: 0, width: WIDTH, height: HEIGHT };
  const source = resolve("landing page.png");
  const metadata = await sharp(source).metadata();
  if (metadata.width !== WIDTH || metadata.height !== HEIGHT)
    throw new Error(
      "Reference dimensions changed; remap regions before tracing",
    );
  // Quantize the whole source first so the proof uses exactly the full scene's palette.
  const quantized = await sharp(source)
    .removeAlpha()
    .blur(0.4)
    .png({ palette: true, colours: 256, dither: 0, effort: 10 })
    .toBuffer();
  const fullData = mergePalette(
    await sharp(quantized).removeAlpha().raw().toBuffer(),
  );
  const data = await sharp(fullData, {
    raw: { width: WIDTH, height: HEIGHT, channels: 3 },
  })
    .extract(crop)
    .raw()
    .toBuffer();
  const regions = regionMap(crop.width, crop.height, crop.left, crop.top);
  const groups = contours(
    data,
    crop.width,
    crop.height,
    regions,
    crop.left,
    crop.top,
  );
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${crop.left} ${crop.top} ${crop.width} ${crop.height}" width="${crop.width}" height="${crop.height}" fill-rule="evenodd">\n<title>Layered risograph studio</title>\n<desc>Vector contours traced from the supplied illustration. No embedded bitmap.</desc>\n<g id="paper" data-layer="paper"><path fill="${PAPER}" d="M0 0H1536V1024H0Z"/></g>\n${groups.map((paths, index) => (paths.length ? `<g id="${REGIONS[index].name}" data-layer="${REGIONS[index].name}">\n${paths.join("\n")}\n</g>` : "")).join("\n")}\n</svg>\n`;
  const output = cropDir
    ? resolve(cropDir, "traced.svg")
    : resolve(args[outputIndex + 1]);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, svg);
  if (cropDir) {
    await sharp(source)
      .extract(crop)
      .png()
      .toFile(resolve(cropDir, "source.png"));
    await sharp(Buffer.from(svg)).png().toFile(resolve(cropDir, "traced.png"));
    await sharp({
      create: {
        width: crop.width * 2,
        height: crop.height,
        channels: 3,
        background: PAPER,
      },
    })
      .composite([
        { input: resolve(cropDir, "source.png"), left: 0, top: 0 },
        { input: resolve(cropDir, "traced.png"), left: crop.width, top: 0 },
      ])
      .png()
      .toFile(resolve(cropDir, "comparison.png"));
  }
  console.log(
    JSON.stringify(
      {
        output,
        colors: COLORS,
        tolerance: TOLERANCE,
        paths: groups.reduce((sum, g) => sum + g.length, 0),
        bytes: Buffer.byteLength(svg),
        gzipBytes: gzipSync(svg).length,
        layers: groups
          .map((g, index) => ({ name: REGIONS[index].name, paths: g.length }))
          .filter((g) => g.paths),
      },
      null,
      2,
    ),
  );
}

await main();
