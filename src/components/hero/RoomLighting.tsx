import { sunlight } from "./sunlight";

type RoomLight = {
  name: string;
  color: string;
  position: [number, number, number];
  target: [number, number, number];
  intensity: number;
  distance: number;
  angle: number;
  mapSize?: number;
};

export const studioCeilingHeight = 4.505;
export const studioConsoleX = 1.2;
export const studioCeilingLights = [
  { name: "Recording studio recessed light", x: 0, z: 0.12 },
];

export const studyTaskLight: RoomLight = {
  name: "Study task lamp",
  color: "#ffca8d",
  position: [-2.59, 1.9, 0.3],
  target: [-2.15, 1.32, 0.4],
  intensity: 1.76,
  distance: 2.2,
  angle: 0.75,
};

const roomLights: Array<RoomLight> = [
  {
    name: "Kitchen ceiling light",
    color: "#ffd3a0",
    position: [1.45, 2.32, 0.15],
    target: [1.4, 0.85, 0.2],
    intensity: 5.5,
    distance: 3,
    angle: 1.2,
  },
  studyTaskLight,
  ...studioCeilingLights.map(({ name, x, z }): RoomLight => ({
    name,
    color: "#ffd4a2",
    position: [x, studioCeilingHeight - 0.04, z],
    target: [x, 2.72, z + 0.08],
    intensity: 5,
    distance: 3.6,
    angle: 1.25,
  })),
  {
    name: "Console display spill",
    color: "#b7e3d5",
    position: [studioConsoleX, 3.78, -0.05],
    target: [1.2, 3.53, 0.42],
    intensity: 0.05,
    distance: 1.3,
    angle: 0.95,
    mapSize: 256,
  },
  {
    name: "Observatory guide light",
    color: "#ffd4ac",
    position: [0.38, 7.28, 0.64],
    target: [0, 7.95, 0.5],
    intensity: 0.65,
    distance: 1.5,
    angle: 1,
    mapSize: 256,
  },
];

export function RoomLighting() {
  return (
    <group name="Room lighting">
      {roomLights.map(({ target, mapSize = 512, ...light }) => (
        <spotLight
          key={light.name}
          {...light}
          penumbra={0.65}
          decay={2}
          castShadow
          shadow-mapSize={[mapSize, mapSize]}
          shadow-camera-near={0.03}
          shadow-camera-far={light.distance}
          shadow-radius={1 + sunlight.diffusion}
          shadow-bias={-0.0001}
          shadow-normalBias={0.008}
        >
          <object3D
            attach="target"
            position={target}
            onUpdate={(object) => object.updateMatrixWorld()}
          />
        </spotLight>
      ))}

      <pointLight
        name="Gaming pink cove light"
        color="#ff78ad"
        position={[0, 6.35, -0.7]}
        intensity={3.5}
        distance={4}
        decay={2}
        castShadow
        shadow-mapSize={[512, 512]}
        shadow-camera-near={0.03}
        shadow-camera-far={4}
        shadow-radius={1 + sunlight.diffusion}
        shadow-bias={-0.0001}
        shadow-normalBias={0.008}
      />

      {/* The ceiling fixtures make the sources of the room washes visible. */}
      <mesh name="Kitchen ceiling mount" position={[1.45, 2.36, 0.15]}>
        <cylinderGeometry args={[0.18, 0.18, 0.02, 24]} />
        <meshStandardMaterial color="#ded0b7" roughness={0.65} />
      </mesh>
      <mesh name="Kitchen ceiling diffuser" position={[1.45, 2.342, 0.15]}>
        <cylinderGeometry args={[0.145, 0.145, 0.018, 24]} />
        <meshStandardMaterial
          color="#ffe5bd"
          emissive="#ffd3a0"
          emissiveIntensity={1.4}
        />
      </mesh>
      <mesh name="Gaming pink ceiling strip" position={[0, 6.56, -1.13]}>
        <boxGeometry args={[4.3, 0.025, 0.03]} />
        <meshStandardMaterial
          color="#ff80b3"
          emissive="#ff5595"
          emissiveIntensity={1.5}
        />
      </mesh>
      <mesh name="Observatory guide LED" position={[0.38, 7.25, 0.64]}>
        <sphereGeometry args={[0.018, 12, 8]} />
        <meshStandardMaterial
          color="#ffe4c5"
          emissive="#ffd4ac"
          emissiveIntensity={0.8}
        />
      </mesh>

      {/* Short-range device glow stays below the room lights and the sunset. */}
      <pointLight
        name="PC cyan glow"
        color="#63dfff"
        position={[1.28, 5.85, 0.68]}
        intensity={0.04}
        distance={0.8}
        decay={2}
      />
      <pointLight
        name="Gaming monitor violet glow"
        color="#b395ff"
        position={[-0.13, 5.98, 0.25]}
        intensity={0.08}
        distance={1.6}
        decay={2}
      />
    </group>
  );
}
