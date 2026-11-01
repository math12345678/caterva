/**
 * The molecule viewer's mathematics: a rotation, a perspective projection
 * and picking, written here so the viewer adds no dependency (three.js is
 * locked in the workspace, but a backbone trace and a few side chains do
 * not need a scene graph, and Canvas 2D draws them on every machine the
 * studio runs on, WebGL or not).
 *
 * Conventions. Model coordinates are the file's, in angstroms, centred on
 * the centroid. A rotation is a row-major 3x3 matrix `m` taking model
 * coordinates to view coordinates: x right, y up, z towards the viewer.
 * The camera looks down -z from `distance` angstroms; the projection maps
 * a view point to canvas pixels with y down.
 */

export type Mat3 = Float64Array; // length 9, row-major

export function identity(): Mat3 {
  return new Float64Array([1, 0, 0, 0, 1, 0, 0, 0, 1]);
}

export function multiply(a: Mat3, b: Mat3): Mat3 {
  const out = new Float64Array(9);
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      out[r * 3 + c] = a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c];
    }
  }
  return out;
}

/** Rotation by `angle` radians about the view's x axis (pitch: positive brings the top towards the viewer and the front down). */
export function rotationX(angle: number): Mat3 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return new Float64Array([1, 0, 0, 0, c, -s, 0, s, c]);
}

/** Rotation by `angle` radians about the view's y axis (yaw: positive turns the front to the right). */
export function rotationY(angle: number): Mat3 {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return new Float64Array([c, 0, s, 0, 1, 0, -s, 0, c]);
}

/**
 * Turn the model as a drag of (dx, dy) pixels would: about the screen's own
 * axes, whatever the current orientation, so dragging right always turns
 * the front to the right. `radiansPerPixel` sets the feel.
 */
export function dragRotate(m: Mat3, dx: number, dy: number, radiansPerPixel = 0.008): Mat3 {
  const yaw = rotationY(dx * radiansPerPixel);
  const pitch = rotationX(dy * radiansPerPixel);
  return orthonormalize(multiply(pitch, multiply(yaw, m)));
}

/**
 * Gram-Schmidt on the rows, so thousands of small rotations do not let
 * rounding shear or scale the model.
 */
export function orthonormalize(m: Mat3): Mat3 {
  const r0 = [m[0], m[1], m[2]];
  const r1 = [m[3], m[4], m[5]];
  const n0 = Math.hypot(r0[0], r0[1], r0[2]) || 1;
  r0[0] /= n0;
  r0[1] /= n0;
  r0[2] /= n0;
  const d = r0[0] * r1[0] + r0[1] * r1[1] + r0[2] * r1[2];
  r1[0] -= d * r0[0];
  r1[1] -= d * r0[1];
  r1[2] -= d * r0[2];
  const n1 = Math.hypot(r1[0], r1[1], r1[2]) || 1;
  r1[0] /= n1;
  r1[1] /= n1;
  r1[2] /= n1;
  const r2 = [r0[1] * r1[2] - r0[2] * r1[1], r0[2] * r1[0] - r0[0] * r1[2], r0[0] * r1[1] - r0[1] * r1[0]];
  return new Float64Array([...r0, ...r1, ...r2]);
}

export function determinant(m: Mat3): number {
  return (
    m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6])
  );
}

export interface Camera {
  /** Rotation from model to view coordinates. */
  rotation: Mat3;
  /** Camera distance from the model's centre, in angstroms. */
  distance: number;
  /** Canvas size in CSS pixels. */
  width: number;
  height: number;
  /** Pixels per angstrom at the model's centre (z = 0). */
  scale: number;
}

/**
 * Project `count` model points (xyz interleaved) into `out` (x, y, z per
 * point): canvas pixels and the view-space depth (positive towards the
 * viewer). Points at or behind the camera get NaN screen coordinates.
 */
export function projectAll(xyz: Float32Array, count: number, cam: Camera, out: Float32Array): void {
  const m = cam.rotation;
  const cx = cam.width / 2;
  const cy = cam.height / 2;
  const f = cam.scale * cam.distance;
  for (let i = 0; i < count; i++) {
    const x = xyz[i * 3];
    const y = xyz[i * 3 + 1];
    const z = xyz[i * 3 + 2];
    const vx = m[0] * x + m[1] * y + m[2] * z;
    const vy = m[3] * x + m[4] * y + m[5] * z;
    const vz = m[6] * x + m[7] * y + m[8] * z;
    const w = cam.distance - vz;
    if (w <= 0.1) {
      out[i * 3] = Number.NaN;
      out[i * 3 + 1] = Number.NaN;
    } else {
      const k = f / w;
      out[i * 3] = cx + vx * k;
      out[i * 3 + 1] = cy - vy * k;
    }
    out[i * 3 + 2] = vz;
  }
}

/** One point, for tests and for placing a label. */
export function project(p: readonly [number, number, number], cam: Camera): [number, number, number] {
  const out = new Float32Array(3);
  projectAll(new Float32Array(p), 1, cam, out);
  return [out[0], out[1], out[2]];
}

/** The scale that fits a sphere of `radius` angstroms inside the canvas with a margin. */
export function fitScale(radius: number, width: number, height: number, margin = 0.88): number {
  const r = Math.max(radius, 1);
  return (Math.min(width, height) / 2 / r) * margin;
}

/**
 * The point nearest (sx, sy) within `maxPx` pixels among `candidates`
 * (indices into the projected array), preferring the one nearer the viewer
 * when two are equally near on screen. Returns -1 when none is close
 * enough.
 */
export function pick(
  projected: Float32Array,
  candidates: ArrayLike<number>,
  sx: number,
  sy: number,
  maxPx: number,
): number {
  let best = -1;
  let bestD = maxPx * maxPx;
  let bestZ = -Infinity;
  for (let k = 0; k < candidates.length; k++) {
    const i = candidates[k];
    const x = projected[i * 3];
    const y = projected[i * 3 + 1];
    if (Number.isNaN(x)) continue;
    const d = (x - sx) * (x - sx) + (y - sy) * (y - sy);
    const z = projected[i * 3 + 2];
    // Within half a pixel counts as a tie, which depth breaks.
    if (d < bestD - 0.25 || (Math.abs(d - bestD) <= 0.25 && z > bestZ)) {
      best = i;
      bestD = d;
      bestZ = z;
    }
  }
  return best;
}
