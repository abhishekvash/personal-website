import {
  Box3,
  CanvasTexture,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  SRGBColorSpace,
  ShaderChunk,
  Vector3,
} from "three";
import type { Group } from "three";

function createPainter(context: CanvasRenderingContext2D) {
  return {
    rect(color: string, x: number, y: number, width: number, height: number) {
      context.fillStyle = color;
      context.fillRect(x, y, width, height);
    },
    text(value: string, color: string, x: number, y: number, size = 18) {
      context.fillStyle = color;
      context.font = `${size}px monospace`;
      context.fillText(value, x, y);
    },
    circle(color: string, x: number, y: number, radius: number) {
      context.fillStyle = color;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    },
    polygon(color: string, points: Array<[number, number]>) {
      context.fillStyle = color;
      context.beginPath();
      points.forEach(([x, y], index) => {
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.closePath();
      context.fill();
    },
  };
}

type Painter = ReturnType<typeof createPainter>;

function drawEditor(p: Painter) {
  p.rect("#101c2f", 0, 0, 640, 360);
  p.rect("#253149", 0, 0, 640, 36);
  p.text("curiosity / studio.tsx", "#b9c7da", 22, 25);
  p.rect("#1b2940", 0, 36, 132, 302);
  p.text("FILES", "#839ab8", 16, 66, 16);
  [72, 92, 63, 82, 55, 73].forEach((width, index) => {
    p.rect(index === 2 ? "#6dbfcd" : "#536883", 24, 90 + index * 26, width, 8);
  });
  p.rect("#233651", 138, 151, 492, 25);
  // Wide, indented syntax tokens read as code even when the display is only 40px wide.
  const lines = [
    [0, 62, 114, 48],
    [0, 48, 74, 98],
    [0, 84, 52, 34],
    [1, 44, 100, 62],
    [2, 75, 46, 110],
    [2, 54, 94, 44],
    [1, 30, 60, 86],
    [0, 44, 92, 55],
  ];
  lines.forEach(([indent, ...widths], row) => {
    const y = 66 + row * 27;
    p.text(String(row + 1), "#637793", 144, y + 8, 14);
    let x = 174 + indent * 24;
    widths.forEach((width, token) => {
      const color = ["#dba0d3", "#86c9d0", "#d9bf86"][(row + token) % 3];
      p.rect(color, x, y, width, 8);
      x += width + 12;
    });
  });
  p.rect("#0c1625", 132, 296, 508, 42);
  p.text("> dev server ready", "#89bda3", 153, 323, 17);
  p.rect("#355a73", 0, 338, 640, 22);
  p.text("main   TypeScript", "#c8e1e6", 16, 354, 14);
}

function drawPreview(p: Painter) {
  p.rect("#d6cfb9", 0, 0, 640, 360);
  p.rect("#344453", 0, 0, 640, 42);
  ["#cb8d85", "#d6b974", "#86b3a2"].forEach((color, index) => {
    p.circle(color, 20 + index * 22, 21, 6);
  });
  p.rect("#202f40", 114, 9, 498, 24);
  p.text("localhost:3000", "#b3c5ca", 133, 27, 16);
  p.text("LITTLE WORLDS", "#304a48", 32, 86, 25);
  p.rect("#4c7064", 34, 129, 202, 17);
  p.rect("#4c7064", 34, 159, 160, 17);
  p.rect("#8b9985", 34, 202, 197, 8);
  p.rect("#8b9985", 34, 219, 169, 8);
  p.rect("#b96d59", 34, 259, 132, 34);
  p.text("EXPLORE", "#f2dfbc", 51, 282, 17);
  // A tiny terrarium in the live browser preview echoes the house's garden.
  p.rect("#b4c0a0", 303, 104, 300, 219);
  p.rect("#849c86", 322, 299, 262, 9);
  p.rect("#a16b55", 403, 243, 99, 46);
  p.rect("#c48a65", 391, 234, 123, 17);
  p.rect("#48664b", 442, 153, 14, 81);
  p.rect("#48664b", 408, 177, 42, 13);
  p.rect("#48664b", 455, 161, 38, 13);
  p.rect("#607f55", 372, 151, 65, 29);
  p.rect("#6d8e60", 393, 133, 44, 20);
  p.rect("#436d55", 476, 133, 61, 30);
  p.rect("#6d8e60", 476, 115, 38, 21);
  p.rect("#799868", 427, 108, 37, 39);
}

function drawDaw(p: Painter) {
  p.rect("#15202b", 0, 0, 640, 360);
  p.rect("#2c3846", 0, 0, 640, 37);
  p.polygon("#8bc3a0", [
    [22, 9],
    [22, 28],
    [39, 19],
  ]);
  p.rect("#9babb5", 56, 12, 14, 14);
  p.circle("#d68a8a", 92, 19, 7);
  p.text("01:08:024", "#c3d9c7", 252, 26, 24);
  p.text("120 BPM", "#aab9c7", 521, 25, 17);
  p.rect("#1e2e3c", 0, 39, 112, 207);
  const colors = ["#6ab6bc", "#85acb4", "#c99b76", "#b69dc8", "#89b393"];
  const labels = ["DRUMS", "BASS", "KEYS", "VOCAL", "PAD"];
  colors.forEach((color, track) => {
    const y = 64 + track * 35;
    p.rect(color, 10, y, 8, 24);
    p.text(labels[track], "#a9bac8", 27, y + 17, 14);
    p.rect("#243440", 119, y, 511, 28);
    for (let bar = 0; bar < 8; bar++) {
      p.rect("#34454f", 125 + bar * 63, 44, 1, 197);
    }
    for (let clip = 0; clip < 3; clip++) {
      const x = 129 + clip * 160 + (track % 2) * 18;
      const width = track === 3 && clip === 0 ? 79 : 137;
      p.rect(color, x, y + 2, width, 24);
      for (let note = 0; note < 13; note++) {
        const height = track < 2 ? 4 + ((note * 7 + clip * 3) % 17) : 4;
        const offset = track < 2 ? (24 - height) / 2 : 4 + ((note * 3) % 14);
        p.rect(
          "#31424d",
          x + 5 + (note * (width - 10)) / 13,
          y + 2 + offset,
          5,
          height,
        );
      }
    }
  });
  p.rect("#f0d8ab", 368, 40, 3, 202);
  p.polygon("#f0d8ab", [
    [360, 39],
    [379, 39],
    [369, 50],
  ]);
  p.rect("#202f3d", 0, 253, 640, 107);
  for (let channel = 0; channel < 10; channel++) {
    const x = 17 + channel * 63;
    p.rect("#344552", x, 267, 46, 82);
    p.rect("#121f2b", x + 8, 279, 9, 58);
    p.rect(
      "#86ba9a",
      x + 8,
      296 + (channel % 3) * 10,
      9,
      41 - (channel % 3) * 10,
    );
    p.rect("#192733", x + 28, 279, 3, 58);
    p.rect("#b6c1bf", x + 23, 305 + (channel % 3) * 6, 13, 6);
  }
}

function drawGame(p: Painter) {
  p.rect("#182848", 0, 0, 640, 360);
  p.circle("#d9c193", 531, 111, 39);
  p.circle("#182848", 513, 95, 33);
  for (let star = 0; star < 18; star++) {
    p.rect("#849fbc", 24 + ((star * 37) % 600), 66 + ((star * 29) % 117), 3, 3);
  }
  p.polygon("#304267", [
    [0, 263],
    [0, 209],
    [82, 143],
    [164, 221],
    [262, 132],
    [391, 250],
    [488, 181],
    [640, 240],
    [640, 360],
    [0, 360],
  ]);
  p.polygon("#40577a", [
    [0, 290],
    [0, 258],
    [96, 223],
    [176, 271],
    [341, 210],
    [436, 287],
    [573, 219],
    [640, 250],
    [640, 360],
    [0, 360],
  ]);
  p.rect("#263954", 0, 302, 640, 58);
  for (const [x, y, width] of [
    [0, 286, 216],
    [266, 235, 128],
    [462, 185, 131],
    [505, 302, 135],
  ]) {
    p.rect("#6e7c94", x, y, width, 14);
    p.rect("#324158", x, y + 14, width, 25);
    p.rect("#a1c7ba", x, y, width, 5);
    for (let brick = 0; brick < width / 24; brick++) {
      p.rect("#4b5b73", x + brick * 24, y + 18, 18, 9);
    }
  }
  [296, 334, 372, 497, 535, 573].forEach((x, index) => {
    p.rect("#dfbb77", x, index < 3 ? 205 : 155, 11, 16);
    p.rect("#f1d9a6", x + 3, index < 3 ? 208 : 158, 3, 8);
  });
  // An original pixel astronaut, mid-jump between platforms.
  p.rect("#ba8399", 211, 189, 12, 25);
  p.rect("#dfded0", 220, 172, 29, 27);
  p.rect("#6fa8ba", 229, 180, 23, 12);
  p.rect("#d2c7c3", 219, 199, 29, 27);
  p.rect("#dfded0", 245, 202, 17, 10);
  p.rect("#a7869d", 215, 225, 13, 19);
  p.rect("#a7869d", 241, 224, 18, 10);
  p.rect("#edc489", 221, 248, 6, 12);
  p.rect("#edc489", 244, 239, 6, 10);
  p.rect("#142238", 0, 0, 640, 42);
  for (let life = 0; life < 3; life++) {
    const x = 20 + life * 32;
    p.polygon("#d993a6", [
      [x, 14],
      [x + 7, 10],
      [x + 13, 15],
      [x + 19, 10],
      [x + 26, 14],
      [x + 26, 21],
      [x + 13, 32],
      [x, 21],
    ]);
  }
  p.text("MOONRUNNER", "#b1c7d4", 244, 28, 22);
  p.text("02400", "#dfcc9c", 535, 28, 22);
}

const screens = [
  { name: "Study_display__screen", label: "Code editor", draw: drawEditor },
  {
    name: "Study_display__screen001",
    label: "Live terrarium preview",
    draw: drawPreview,
  },
  { name: "Studio_display__screen", label: "DAW arrangement", draw: drawDaw },
  {
    name: "Gaming_ultrawide__screen",
    label: "Moonrunner game",
    draw: drawGame,
  },
];

export function installScreenContent(scene: Group) {
  const previewTime = { value: 0 };
  scene.traverse((object) => {
    if (
      /^(Display_star|Pixel_star|Synthwave_terrain|Tiny_sunset)/.test(
        object.name,
      ) ||
      /^(Study|Studio)_display__luminous_flower_diagram/.test(object.name)
    ) {
      object.visible = false;
    }
  });
  scene.updateMatrixWorld(true);

  for (const { name, label, draw } of screens) {
    const original = scene.getObjectByName(name);
    if (!(original instanceof Mesh)) continue;
    const bounds = new Box3().setFromObject(original);
    const size = bounds.getSize(new Vector3());
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = Math.round((canvas.width * size.y) / size.x);
    const context = canvas.getContext("2d");
    if (!context) throw new Error(`Could not draw the ${label} screen.`);
    context.scale(canvas.width / 640, canvas.height / 360);
    draw(createPainter(context));

    // Paint once, mipmap for the distant camera, and let scene disposal own the texture.
    const texture = new CanvasTexture(canvas);
    texture.name = label;
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = 4;
    const material = new MeshBasicMaterial({ map: texture, color: "#b9b9b9" });
    if (draw === drawPreview) {
      // Warp only the foliage. Browser chrome, text, pot, and texture remain static.
      material.customProgramCacheKey = () => "terrarium-preview-motion-v2";
      material.onBeforeCompile = (shader) => {
        shader.uniforms.uPreviewTime = previewTime;
        shader.fragmentShader = `uniform float uPreviewTime;\n${shader.fragmentShader}`;
        shader.fragmentShader = shader.fragmentShader.replace(
          "#include <map_fragment>",
          /* glsl */ `
            vec2 previewUv = vMapUv;
            float height = clamp((vMapUv.y - 0.35) / 0.35, 0.0, 1.0);
            float foliage = smoothstep(0.475, 0.51, vMapUv.x)
              * (1.0 - smoothstep(0.90, 0.94, vMapUv.x))
              * smoothstep(0.35, 0.47, vMapUv.y)
              * (1.0 - smoothstep(0.71, 0.76, vMapUv.y));
            previewUv.x += sin(uPreviewTime * 1.4 + height * 1.2)
              * height * foliage * 0.075;
            if (foliage > 0.0) previewUv.x = clamp(previewUv.x, 0.475, 0.94);
            ${ShaderChunk.map_fragment.replace("vMapUv", "previewUv")}
            vec2 moteA = vec2(0.55 + 0.035 * sin(uPreviewTime * 1.2),
              0.46 + 0.14 * sin(uPreviewTime * 0.9));
            vec2 moteB = vec2(0.87 + 0.03 * sin(uPreviewTime),
              0.44 + 0.17 * cos(uPreviewTime * 0.8));
            vec2 distanceA = (vMapUv - moteA) * vec2(640.0, 360.0);
            vec2 distanceB = (vMapUv - moteB) * vec2(640.0, 360.0);
            float pollen = exp(-dot(distanceA, distanceA) / 90.0)
              + exp(-dot(distanceB, distanceB) / 90.0);
            diffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0, 0.78, 0.24),
              min(pollen, 1.0) * 0.95);
          `,
        );
      };
    }
    const display = new Mesh(new PlaneGeometry(size.x, size.y), material);
    display.name = `${label} content`;
    bounds.getCenter(display.position);
    display.position.z = bounds.max.z + 0.001;
    original.visible = false;
    scene.add(display);
  }
  return (time: number) => {
    previewTime.value = time;
  };
}
