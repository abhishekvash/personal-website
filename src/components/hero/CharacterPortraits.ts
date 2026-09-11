import {
  Box3,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  SRGBColorSpace,
  TextureLoader,
  Vector3,
} from "three";
import type { Group } from "three";

const portraits = [
  {
    background: "Character_art__background",
    image: "/scene/portraits/poolside.webp",
    name: "Poolside anime portrait",
  },
  {
    background: "Character_art__background001",
    image: "/scene/portraits/pink-haired.webp",
    name: "Pink-haired anime portrait",
  },
];

export async function installCharacterPortraits(scene: Group) {
  const loader = new TextureLoader();
  const results = await Promise.allSettled(
    portraits.map(({ image }) => loader.loadAsync(image)),
  );
  const failure = results.find((result) => result.status === "rejected");
  if (failure) {
    // Wait for both requests so a late success cannot leave an orphaned texture.
    results.forEach((result) => {
      if (result.status === "fulfilled") result.value.dispose();
    });
    throw new Error("Could not load the gaming-room portraits.", {
      cause: failure.reason,
    });
  }

  scene.traverse((object) => {
    if (
      object.name.startsWith("Character_art__") &&
      !object.name.startsWith("Character_art__brass_frame")
    ) {
      object.visible = false;
    }
  });
  scene.updateMatrixWorld(true);

  results.forEach((result, index) => {
    if (result.status !== "fulfilled") return;
    const { background, name } = portraits[index];
    const texture = result.value;
    const original = scene.getObjectByName(background);
    if (!(original instanceof Mesh)) {
      texture.dispose();
      return;
    }
    const bounds = new Box3().setFromObject(original);
    const size = bounds.getSize(new Vector3());
    texture.name = name;
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = 4;
    // Fill the existing frames without stretching differently proportioned artwork.
    const image = texture.image;
    const imageAspect = image.naturalWidth / image.naturalHeight;
    const frameAspect = size.x / size.y;
    if (imageAspect > frameAspect) {
      texture.repeat.x = frameAspect / imageAspect;
      texture.offset.x = (1 - texture.repeat.x) / 2;
    } else {
      texture.repeat.y = imageAspect / frameAspect;
      texture.offset.y = (1 - texture.repeat.y) / 2;
    }
    const portrait = new Mesh(
      new PlaneGeometry(size.x, size.y),
      new MeshStandardMaterial({
        map: texture,
        emissiveMap: texture,
        emissive: "#ffffff",
        emissiveIntensity: 0.12,
        roughness: 1,
      }),
    );
    portrait.name = name;
    bounds.getCenter(portrait.position);
    portrait.position.z = bounds.max.z + 0.001;
    portrait.receiveShadow = true;
    scene.add(portrait);
  });
}
