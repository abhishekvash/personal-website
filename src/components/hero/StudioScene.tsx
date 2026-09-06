import { useId } from "react";

import { SceneAtmosphere } from "./SceneAtmosphere";
import artworkUrl from "./layers/studio.svg?url";

const layers = [
  "building",
  "workspace",
  "kitchen",
  "audio",
  "computer",
  "observatory",
  "bonsai",
  "blossoms",
] as const;

const hotspots = [
  {
    name: "room-observatory",
    path: "M696 101Q751 48 811 88Q850 120 842 172Q824 224 772 223Q713 219 697 171Z",
  },
  {
    name: "room-computer",
    path: "M598 326L866 302L950 329L963 473L900 497L585 516Z",
  },
  {
    name: "room-audio",
    path: "M518 517L909 505Q955 508 961 540L969 643Q948 661 917 665L508 689Q485 682 491 651L491 548Q493 526 518 517Z",
  },
  {
    name: "room-workspace",
    path: "M496 740L752 709L760 887Q763 915 741 918L487 937Q469 934 469 910L470 771Q470 749 496 740Z",
  },
  { name: "room-kitchen", path: "M775 708L1061 679L1082 869L778 913Z" },
  {
    name: "bonsai",
    path: "M981 56L1092 0H1495L1536 50V469L1420 515L1385 596Q1490 597 1480 681L1470 765Q1420 834 1280 828Q1140 817 1138 747L1138 657Q1145 605 1256 590L1207 489L1035 465L1003 371L1031 273L949 175Z",
  },
] as const;

/** The detailed contours stay in a cached SVG asset, not React's JS payload. */
export function StudioScene() {
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;
  const grainId = `${id}-paper-grain`;
  const buildingClipId = `${id}-building-outline`;
  const bonsaiClipId = `${id}-bonsai-outline`;

  return (
    <svg
      className="isolate block aspect-3/2 h-auto w-full overflow-hidden"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 1536 1024"
      width="1536"
      height="1024"
      fillRule="evenodd"
      role="img"
      aria-labelledby={`${titleId} ${descriptionId}`}
      focusable="false"
    >
      <title id={titleId}>A little world of curiosity</title>
      <desc id={descriptionId}>
        A blue and cream, three-storey creative studio beneath an observatory.
        Its open rooms contain a computer desk, a recording studio, a workspace
        and a tiny kitchen. A pink flowering bonsai stands beside it against a
        warm beige background, all illustrated in textured risograph inks.
      </desc>
      <defs>
        {/* Object-owned contours include table pixels around their bases. */}
        <clipPath id={buildingClipId}>
          <path d="M0 0H1536V635H1095Q1107 640 1105 666L1107 850L1125 861Q1132 877 1123 895L1100 903L1098 926L1089 931L1064 929L1063 923L1032 925L1000 927L952 932L896 937L859 942L856 948L834 950L830 948L768 954L704 962L640 969L638 975L616 976L599 975L590 972L536 978L489 982L478 980L473 992L463 996L445 993L437 988L424 988L418 975L407 971L393 958L381 946L368 937L351 919L338 909L324 895L321 879L300 853L298 839L309 826L320 816L328 635H0Z" />
        </clipPath>
        <clipPath id={bonsaiClipId}>
          <path d="M0 0H1536V595H1450Q1488 612 1481 668L1467 770Q1464 792 1447 802Q1390 830 1304 830Q1200 828 1160 803Q1145 792 1140 765L1137 672Q1132 618 1180 603V595H0Z" />
        </clipPath>
        <filter id={grainId} x="0" y="0" width="100%" height="100%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.85"
            numOctaves="3"
            seed="12"
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
      </defs>
      <g aria-hidden="true">
        <g data-layer="paper" className="fill-scene-paper">
          <path d="M0 0H1536V1024H0Z" />
          <path
            className="opacity-20 mix-blend-soft-light"
            d="M0 0H1536V1024H0Z"
            filter={`url(#${grainId})`}
          />
        </g>
        {layers.map((layer) => (
          <g
            key={layer}
            data-layer={layer}
            clipPath={
              layer === "blossoms"
                ? undefined
                : `url(#${layer === "bonsai" ? bonsaiClipId : buildingClipId})`
            }
          >
            <use href={`${artworkUrl}#${layer}`} />
          </g>
        ))}
        <SceneAtmosphere />
        <g
          data-layer="future-hotspots"
          className="pointer-events-none fill-none"
        >
          {hotspots.map(({ name, path }) => (
            <path
              key={name}
              id={`${id}-${name}`}
              data-hotspot={name}
              d={path}
            />
          ))}
        </g>
      </g>
    </svg>
  );
}
