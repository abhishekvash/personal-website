export type RoomLight = {
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
