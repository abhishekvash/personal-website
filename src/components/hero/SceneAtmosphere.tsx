/** Small accents only: the traced building and tree never move. */
export function SceneAtmosphere() {
  return (
    <g
      data-layer="ambient-accents"
      className="pointer-events-none motion-reduce:hidden [&_path]:[animation-play-state:paused] group-data-[motion=playing]/hero:[&_path]:[animation-play-state:running]"
    >
      <g data-layer="screen-light" className="fill-scene-screen">
        <path
          className="animate-studio-glow opacity-0"
          d="M681 335L772 329L776 391L687 401Z"
        />
        <path
          className="animate-studio-glow opacity-0 [animation-delay:-4s]"
          d="M858 518L929 513L935 583L864 592Z"
        />
        <path
          className="animate-studio-glow opacity-0 [animation-delay:-7s]"
          d="M499 751L577 746L578 800L501 807Z"
        />
      </g>
      <g data-layer="cooking-steam" className="fill-scene-steam">
        <g transform="translate(855 768)">
          <path
            className="animate-studio-steam opacity-0"
            d="M-5 0C-17-13 10-22-1-35C-13-49 8-57 1-72C18-58-5-46 8-34C21-18-3-10 6 0Z"
          />
        </g>
        <g transform="translate(951 743)">
          <path
            className="animate-studio-steam opacity-0 [animation-delay:-3.5s] [animation-duration:8s]"
            d="M-3 0C-12-12 10-20 1-31C-10-44 9-53 2-63C18-48-2-42 9-29C18-16-3-8 5 0Z"
          />
        </g>
      </g>
      <g data-layer="drifting-petals" className="fill-scene-petal">
        <g transform="translate(1097 470)">
          <path
            className="animate-studio-petal opacity-0"
            d="M0 0C-11-8-14 1-7 8C-2 11 4 8 0 0Z"
          />
        </g>
        <g transform="translate(1440 490)">
          <path
            className="animate-studio-petal opacity-0 [animation-delay:-4s] [animation-duration:15s]"
            d="M0 0C-8-10-15-3-10 5C-6 12 1 8 0 0Z"
          />
        </g>
        <g transform="translate(1190 544)">
          <path
            className="animate-studio-petal opacity-0 [animation-delay:-9s] [animation-duration:17s]"
            d="M0 0C-7-8-12-2-7 5C-1 10 4 7 0 0Z"
          />
        </g>
      </g>
    </g>
  );
}
