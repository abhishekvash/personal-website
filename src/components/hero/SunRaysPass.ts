import { Matrix4, Vector2, Vector3 } from "three";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import type {
  Camera,
  DirectionalLight,
  WebGLRenderTarget,
  WebGLRenderer,
} from "three";

const fragmentShader = /* glsl */ `
  varying vec2 vUv;
  uniform sampler2D tDiffuse;
  uniform sampler2D sceneDepth;
  uniform highp sampler2DShadow sunShadow;
  uniform mat4 inverseProjection;
  uniform mat4 cameraWorld;
  uniform mat4 shadowMatrix;
  uniform vec3 sunColor;
  uniform float sunIntensity;
  uniform vec2 shadowTexelSize;
  uniform float shadowRadius;

  vec3 worldPosition(float depth) {
    vec4 view = inverseProjection * vec4(vUv * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    return (cameraWorld * vec4(view.xyz / view.w, 1.0)).xyz;
  }

  vec2 intersectBox(vec3 origin, vec3 direction, vec3 low, vec3 high) {
    vec3 inverseDirection = sign(direction + vec3(0.00000001)) / max(abs(direction), vec3(0.00001));
    vec3 a = (low - origin) * inverseDirection;
    vec3 b = (high - origin) * inverseDirection;
    vec3 nearPlane = min(a, b);
    vec3 farPlane = max(a, b);
    return vec2(max(max(nearPlane.x, nearPlane.y), nearPlane.z),
                min(min(farPlane.x, farPlane.y), farPlane.z));
  }

  bool inRoom(vec3 p) {
    bool study = p.y > 0.54 && p.y < 2.34 && abs(p.x) < 3.08 && p.z > -1.5 && p.z < 1.65;
    bool studio = p.y > 2.67 && p.y < 4.47 && abs(p.x) < 2.78 && p.z > -1.34 && p.z < 1.49;
    bool gaming = p.y > 4.8 && p.y < 6.6 && abs(p.x) < 2.48 && p.z > -1.17 && p.z < 1.32;
    return study || studio || gaming;
  }

  void main() {
    vec4 surface = texture2D(tDiffuse, vUv);
    vec3 origin = worldPosition(0.0);
    vec3 direction = normalize((cameraWorld * vec4(0.0, 0.0, -1.0, 0.0)).xyz);
    vec2 interval = intersectBox(origin, direction, vec3(-3.08, 0.54, -1.5), vec3(3.08, 6.6, 1.65));
    float surfaceDistance = dot(worldPosition(texture2D(sceneDepth, vUv).r) - origin, direction);
    float start = max(interval.x, 0.0);
    float end = min(interval.y, surfaceDistance);
    if (end <= start) {
      gl_FragColor = surface;
      return;
    }

    // Stable jitter avoids marching bands without a continuously running render loop.
    float jitter = fract(dot(gl_FragCoord.xy, vec2(0.754877, 0.56984)));
    float stepLength = (end - start) / 48.0;
    float scattering = 0.0;
    for (int i = 0; i < 48; i++) {
      vec3 p = origin + direction * (start + (float(i) + jitter) * stepLength);
      if (!inRoom(p)) continue;
      vec4 shadow = shadowMatrix * vec4(p, 1.0);
      vec3 coordinate = shadow.xyz / shadow.w;
      if (any(lessThan(coordinate, vec3(0.0))) || any(greaterThan(coordinate, vec3(1.0)))) continue;
      // Sample the actual sun shadow map: walls, furniture, and foliage all block the shafts.
      // Match the surface shader's normalized five-tap disk filter.
      float visibility = 0.0;
      float rotation = jitter * 6.283185;
      for (int tap = 0; tap < 5; tap++) {
        float radius = sqrt((float(tap) + 0.5) / 5.0);
        float angle = float(tap) * 2.399963 + rotation;
        vec2 offset = vec2(cos(angle), sin(angle)) * radius * shadowRadius * shadowTexelSize;
        visibility += texture(sunShadow, vec3(coordinate.xy + offset, coordinate.z - 0.00015));
      }
      scattering += visibility * 0.2 * stepLength;
    }

    vec3 shafts = sunColor * sunIntensity * scattering * 0.075;
    gl_FragColor = vec4(surface.rgb + shafts, surface.a);
  }
`;

/** Single-scattering approximation, bounded to room air and clipped by scene depth. */
export class SunRaysPass extends ShaderPass {
  constructor(
    private camera: Camera,
    private sun: DirectionalLight,
  ) {
    super({
      uniforms: {
        tDiffuse: { value: null },
        sceneDepth: { value: null },
        sunShadow: { value: null },
        inverseProjection: { value: new Matrix4() },
        cameraWorld: { value: new Matrix4() },
        shadowMatrix: { value: new Matrix4() },
        sunColor: { value: new Vector3() },
        sunIntensity: { value: 0 },
        shadowTexelSize: { value: new Vector2() },
        shadowRadius: { value: 1 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader,
    });
  }

  override render(
    renderer: WebGLRenderer,
    writeBuffer: WebGLRenderTarget,
    readBuffer: WebGLRenderTarget,
    deltaTime: number,
    maskActive: boolean,
  ) {
    // RenderPass has just produced both depth textures, including on the first frame.
    this.uniforms.sceneDepth.value = readBuffer.depthTexture;
    this.uniforms.sunShadow.value = this.sun.shadow.map?.depthTexture;
    this.uniforms.inverseProjection.value.copy(
      this.camera.projectionMatrixInverse,
    );
    this.uniforms.cameraWorld.value.copy(this.camera.matrixWorld);
    this.uniforms.shadowMatrix.value.copy(this.sun.shadow.matrix);
    this.uniforms.sunColor.value.set(
      this.sun.color.r,
      this.sun.color.g,
      this.sun.color.b,
    );
    this.uniforms.sunIntensity.value = this.sun.intensity;
    this.uniforms.shadowTexelSize.value.set(
      1 / this.sun.shadow.mapSize.x,
      1 / this.sun.shadow.mapSize.y,
    );
    this.uniforms.shadowRadius.value = this.sun.shadow.radius;
    super.render(renderer, writeBuffer, readBuffer, deltaTime, maskActive);
  }
}
