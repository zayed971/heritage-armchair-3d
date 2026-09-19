"""Procedurally model my carved classical armchair from phone photos. Run: blender -b -P build_chair.py"""
import bpy, bmesh, math
from math import sin, cos, pi, radians
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "tex"
OUT = ROOT / "out"
WOOD_TILE = 0.6
FAB_W, FAB_H = 0.30, 0.89

# ---------------------------------------------------------------- mesh builder
class MB:
    def __init__(self):
        self.v, self.f, self.uv, self.n = [], [], [], 0

    def add(self, verts, faces, fuvs):
        verts = np.asarray(verts, dtype=float).reshape(-1, 3)
        off = self.n
        self.v.append(verts)
        self.n += len(verts)
        for fc, u in zip(faces, fuvs):
            self.f.append(tuple(i + off for i in fc))
            self.uv.append(u)

    def build(self, name, mat, recalc=True, sharp_deg=42):
        me = bpy.data.meshes.new(name)
        me.from_pydata(np.vstack(self.v).tolist(), [], self.f)
        uvl = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, fu in zip(me.polygons, self.uv):
            for li, uvc in zip(poly.loop_indices, fu):
                uvl.data[li].uv = uvc
        if recalc:
            bm = bmesh.new(); bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me); bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=radians(sharp_deg))
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        return ob


def norm(v):
    v = np.asarray(v, float)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)


def catmull(P, n_per=10):
    P = np.asarray(P, float)
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        for t in np.linspace(0, 1, n_per, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return np.array(out)


def rrect(w, h, r, n=5):
    r = min(r, w / 2 - 1e-4, h / 2 - 1e-4)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                       (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for k in range(n + 1):
            a = radians(a0 + 90 * k / n)
            pts.append((cx + r * cos(a), cy + r * sin(a)))
    return np.array(pts)


def circle(r, n=10):
    return np.array([(r * cos(2 * pi * k / n), r * sin(2 * pi * k / n)) for k in range(n)])


def loft(mb, P, secfn, ref=(1, 0, 0), tile=WOOD_TILE, caps=True, uoff=0.0):
    """Sweep per-station closed sections along path P. Grain (texture U) runs along the path."""
    P = np.asarray(P, float); N = len(P)
    T = np.gradient(P, axis=0); T = norm(T)
    ref = np.asarray(ref, float)
    A = norm(ref[None, :] - (T @ ref)[:, None] * T)
    Bv = np.cross(T, A)
    secs = [np.asarray(secfn(i), float) for i in range(N)]
    M = len(secs[0])
    V = np.zeros((N, M, 3))
    for i in range(N):
        V[i] = P[i] + secs[i][:, :1] * A[i] + secs[i][:, 1:2] * Bv[i]
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]) / tile + uoff
    s0 = secs[N // 2]
    c = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(np.vstack([s0, s0[:1]]), axis=0), axis=1))]) / tile
    faces, fuv = [], []
    idx = lambda i, j: i * M + (j % M)
    for i in range(N - 1):
        for j in range(M):
            faces.append((idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)))
            fuv.append(((s[i], c[j]), (s[i], c[j + 1]), (s[i + 1], c[j + 1]), (s[i + 1], c[j])))
    if caps:
        faces.append(tuple(idx(0, j) for j in reversed(range(M))))
        fuv.append(tuple((secs[0][j][0] / tile, secs[0][j][1] / tile) for j in reversed(range(M))))
        faces.append(tuple(idx(N - 1, j) for j in range(M)))
        fuv.append(tuple((secs[-1][j][0] / tile, secs[-1][j][1] / tile) for j in range(M)))
    mb.add(V.reshape(-1, 3), faces, fuv)


def tube(mb, P, r, n=8, tile=WOOD_TILE, ref=(1, 0, 0)):
    rs = np.full(len(P), r) if np.isscalar(r) else np.asarray(r)
    loft(mb, P, lambda i: circle(rs[i], n), ref=ref, tile=tile)


def lathe(mb, prof, C, axis=(0, 0, 1), seg=32, tile=WOOD_TILE):
    """prof: list of (h, r) along axis from centre C."""
    A = norm(axis); tmp = np.array([1.0, 0, 0]) if abs(A[0]) < 0.9 else np.array([0, 1.0, 0])
    E1 = norm(np.cross(A, tmp)); E2 = np.cross(A, E1)
    C = np.asarray(C, float); prof = np.asarray(prof, float); K = len(prof)
    V = np.zeros((K, seg, 3))
    for k, (h, r) in enumerate(prof):
        for j in range(seg):
            a = 2 * pi * j / seg
            V[k, j] = C + A * h + r * (cos(a) * E1 + sin(a) * E2)
    d = np.concatenate([[0], np.cumsum(np.hypot(np.diff(prof[:, 0]), np.diff(prof[:, 1])))]) / tile
    rav = max(prof[:, 1].mean(), 1e-3)
    faces, fuv = [], []
    idx = lambda k, j: k * seg + (j % seg)
    for k in range(K - 1):
        for j in range(seg):
            faces.append((idx(k, j), idx(k, j + 1), idx(k + 1, j + 1), idx(k + 1, j)))
            c0, c1 = 2 * pi * rav * j / seg / tile, 2 * pi * rav * (j + 1) / seg / tile
            fuv.append(((d[k], c0), (d[k], c1), (d[k + 1], c1), (d[k + 1], c0)))
    for k in (0, K - 1):
        if prof[k, 1] > 1e-5:
            faces.append(tuple(idx(k, j) for j in range(seg)))
            fuv.append(tuple((V[k, j][0] / tile, V[k, j][1] / tile) for j in range(seg)))
    mb.add(V.reshape(-1, 3), faces, fuv)


def ellipsoid(mb, C, A1, A2, A3, nu=12, nv=7):
    C, A1, A2, A3 = (np.asarray(x, float) for x in (C, A1, A2, A3))
    V, faces, fuv = [], [], []
    for i in range(nv + 1):
        th = pi * i / nv
        for j in range(nu):
            ph = 2 * pi * j / nu
            V.append(C + A1 * sin(th) * cos(ph) + A2 * sin(th) * sin(ph) + A3 * cos(th))
    idx = lambda i, j: i * nu + (j % nu)
    for i in range(nv):
        for j in range(nu):
            faces.append((idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)))
            fuv.append(((i * .02, j * .02), (i * .02, j * .02 + .02), (i * .02 + .02, j * .02 + .02), (i * .02 + .02, j * .02)))
    mb.add(V, faces, fuv)


def smooth_profile(ctrl, sub=5):
    ctrl = np.asarray(ctrl, float); out = []
    for a, b in zip(ctrl[:-1], ctrl[1:]):
        for t in np.linspace(0, 1, sub, endpoint=False):
            s = t * t * (3 - 2 * t)
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * s))
    out.append(tuple(ctrl[-1]))
    return out

# ---------------------------------------------------------------- back frame
RAKE = radians(13)
SEAT_Z = 0.40
Y0 = 0.2155
BOW = 0.035


def Bk(u, v, w):
    u, v, w = np.broadcast_arrays(np.asarray(u, float), np.asarray(v, float), np.asarray(w, float))
    w2 = w + BOW * (1 - (u / 0.29) ** 2)
    return np.stack([u, Y0 + v * sin(RAKE) + w2 * cos(RAKE), SEAT_Z + v * cos(RAKE) - w2 * sin(RAKE)], -1)


V_BR0, V_P0, V_P1, V_F1, V_TR1 = 0.145, 0.180, 0.540, 0.605, 0.735
STILE_W, STILE_HALF = 0.036, 0.018


def stile_u(v):
    return 0.178 + 0.055 * np.clip((np.asarray(v, float) - 0.18) / 0.36, 0, 1.3)


def arch(u):
    return 0.015 * (1 - np.clip(np.abs(u) / 0.175, 0, 1) ** 2)


def panel_hw(v):
    return stile_u(v) - STILE_HALF + 0.003


def hw_seat(y):
    return 0.195 + (0.23 - y) / 0.50 * 0.075


wood, fabric, trim = MB(), MB(), MB()

# ---------------------------------------------------------------- stiles + sabre back legs
for sx in (1, -1):
    top_of_leg = Bk(0.178, 0.0, 0.0)
    ctrl = [(0.196, top_of_leg[1] + 0.125, 0.0), (0.190, top_of_leg[1] + 0.062, 0.14),
            (0.182, top_of_leg[1] + 0.012, 0.29), tuple(top_of_leg)]
    for v in (0.12, 0.25, 0.40, 0.52, 0.625):
        ctrl.append(tuple(Bk(stile_u(v), v, 0.0)))
    P = catmull(ctrl, 9); P[:, 0] *= sx
    n = len(P)
    depth = np.interp(np.linspace(0, 1, n), [0, 0.42, 0.6, 1], [0.034, 0.052, 0.046, 0.040])
    loft(wood, P, lambda i: rrect(STILE_W, depth[i], 0.006), ref=(1, 0, 0))

# ---------------------------------------------------------------- top rail (rolled scroll back)
RAIL_H, RAIL_T, ROLL_R, W_F = V_TR1 - V_F1, 0.038, 0.033, -0.023
prof = [(W_F, 0.0), (W_F, RAIL_H - ROLL_R)]
cw, cv = W_F + ROLL_R, RAIL_H - ROLL_R
for k in range(1, 19):
    a = radians(180 - 270 * k / 18)
    prof.append((cw + ROLL_R * cos(a), cv + ROLL_R * sin(a)))
prof += [(W_F + RAIL_T, cv - ROLL_R - 0.006), (W_F + RAIL_T, 0.0)]
prof = np.array(prof)
us = np.linspace(-0.278, 0.278, 49)
M = len(prof)
V = np.array([[Bk(u, V_F1 + pv, pw) for (pw, pv) in prof] for u in us]).reshape(-1, 3)
per = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(np.vstack([prof, prof[:1]]), axis=0), axis=1))]) / WOOD_TILE
faces, fuv = [], []
idx = lambda i, j: i * M + (j % M)
for i in range(len(us) - 1):
    for j in range(M):
        faces.append((idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j)))
        fuv.append(((us[i] / WOOD_TILE, per[j]), (us[i] / WOOD_TILE, per[j + 1]),
                    (us[i + 1] / WOOD_TILE, per[j + 1]), (us[i + 1] / WOOD_TILE, per[j])))
for i in (0, len(us) - 1):
    faces.append(tuple(idx(i, j) for j in range(M)))
    fuv.append(tuple((prof[j][0] / WOOD_TILE, prof[j][1] / WOOD_TILE) for j in range(M)))
wood.add(V, faces, fuv)

# volute spirals on rail ends + carved leaf bands over the rolled ends
for sx in (1, -1):
    ue = sx * 0.2795
    ph = np.linspace(0, 2 * pi * 2.3, 70)
    rho = np.linspace(0.027, 0.004, 70)
    Ps = Bk(ue, V_F1 + cv + rho * np.sin(ph + 2.4), cw + rho * np.cos(ph + 2.4))
    tube(wood, Ps, 0.0042 * np.sin(np.linspace(0.02, 0.98, 70) * pi) ** 0.35, n=8, ref=(1, 0, 0))
    ellipsoid(wood, Bk(ue, V_F1 + cv, cw), (0.004 * sx, 0, 0), (0, 0.006, 0), (0, 0, 0.006), 10, 6)
    # leaf band path: up the front face then over the roll
    path_wv = [(W_F, t) for t in np.linspace(0.004, RAIL_H - ROLL_R, 9)]
    path_wv += [(cw + ROLL_R * cos(radians(a)), cv + ROLL_R * sin(radians(a))) for a in np.linspace(170, -40, 12)]
    path_wv = np.array(path_wv)
    ub = sx * 0.256
    for k in range(len(path_wv) - 1):
        (w0, v0), (w1, v1) = path_wv[k], path_wv[k + 1]
        t = norm(np.array([0, w1 - w0, v1 - v0]))          # (u, w, v) local tangent
        nrm = np.array([0, -t[2], t[1]])                   # outward normal in (w, v)
        for side in (1, -1):
            c_loc = np.array([ub + side * 0.0085, (w0 + w1) / 2 + nrm[1] * 0.001, (v0 + v1) / 2 + nrm[2] * 0.001])
            d_long = norm(np.array([side * 0.75, t[1], t[2]]))
            d_wide = norm(np.cross(d_long, np.array([0, nrm[1], nrm[2]])))
            def L2W(p):
                return Bk(p[0], V_F1 + p[2], p[1])
            C = L2W(c_loc); e = 1e-3
            A1 = (L2W(c_loc + d_long * e) - C) / e * 0.011
            A2 = (L2W(c_loc + d_wide * e) - C) / e * 0.0062
            A3 = (L2W(c_loc + np.array([0, nrm[1], nrm[2]]) * e) - C) / e * 0.0034
            ellipsoid(wood, C, A1, A2, A3, 10, 5)
    rib = np.array([Bk(ub, V_F1 + v_, w_ - 0.0012 if k < 9 else w_) for k, (w_, v_) in enumerate(path_wv)])
    tube(wood, catmull(rib, 3), 0.0024, n=6, ref=(1, 0, 0))

# ---------------------------------------------------------------- cartouche (oval medallion + floral relief)
CV = V_F1 + 0.082
def cart(u, dv, lift=0.0):
    return Bk(u, CV + dv, W_F - lift)
th = np.linspace(0, 2 * pi, 49)
for (ra, rb, rr) in ((0.080, 0.034, 0.0042), (0.070, 0.0265, 0.0022)):
    ring = np.array([cart(ra * cos(t), rb * sin(t), 0.0005) for t in th])
    tube(wood, ring, rr, n=8, ref=(0, 1, 0))
ellipsoid(wood, cart(0, 0, 0.001), (0.0085, 0, 0), (0, 0.002, 0.0085), (0, -0.005, 0.001), 12, 6)
for k in range(6):
    a = k * pi / 3
    c = cart(0.0125 * cos(a), 0.0115 * sin(a), 0.0008)
    d = norm(cart(0.02 * cos(a), 0.02 * sin(a)) - cart(0, 0))
    up = norm(np.cross(d, (0, -1, 0.2)))
    ellipsoid(wood, c, d * 0.0075, up * 0.0042, np.array([0, -0.003, 0.0007]), 10, 5)
for sx in (1, -1):
    for (sgn, reach) in ((1, 0.058), (-1, 0.050)):
        ts = np.linspace(0, 1, 26)
        uu = sx * (0.016 + reach * ts)
        vv = sgn * (0.013 * np.sin(ts * pi * 1.15) - 0.004 * ts)
        curl_a = np.linspace(0, 2 * pi * 0.9, 12)
        cu = uu[-1] + sx * 0.0055 * np.sin(curl_a)
        cvv = vv[-1] - sgn * 0.0055 * (1 - np.cos(curl_a))
        U = np.concatenate([uu, cu[1:]]); Vv = np.concatenate([vv, cvv[1:]])
        Pp = np.array([cart(a_, b_, 0.0012) for a_, b_ in zip(U, Vv)])
        tube(wood, Pp, np.linspace(0.0036, 0.0016, len(Pp)), n=7, ref=(0, 1, 0))
        for tt in (0.3, 0.55, 0.8):
            i = int(tt * 25)
            c = cart(uu[i], vv[i] + sgn * 0.0065, 0.0008)
            d = norm(cart(uu[i] + sx * 0.01, vv[i] + sgn * 0.012) - cart(uu[i], vv[i]))
            ellipsoid(wood, c, d * 0.0078, norm(np.cross(d, (0, -1, 0.2))) * 0.0034, np.array([0, -0.0028, 0.0006]), 8, 5)

# ---------------------------------------------------------------- pierced fretwork band
FT = 0.018
band_hw = float(stile_u((V_P1 + V_F1) / 2)) - STILE_HALF + 0.004
cell_w, cell_h = 2 * band_hw / 4, V_F1 - V_P1
NA = 72
ang = np.linspace(0, 2 * pi, NA, endpoint=False)
def hole_r(a):
    ax, ay, p = 0.0405, 0.0215, 4.0
    r = (np.abs(np.cos(a) / ax) ** p + np.abs(np.sin(a) / ay) ** p) ** (-1 / p)
    for a0 in (pi / 2, 3 * pi / 2):
        dd = np.angle(np.exp(1j * (a - a0)))
        r = r * (1 - 0.50 * np.exp(-(dd / 0.30) ** 2))
    return r
def rect_r(a):
    return np.minimum(cell_w / 2 / np.maximum(np.abs(np.cos(a)), 1e-9), cell_h / 2 / np.maximum(np.abs(np.sin(a)), 1e-9))
for c in range(4):
    uc = -band_hw + cell_w * (c + 0.5); vc = (V_P1 + V_F1) / 2
    hr, rr = hole_r(ang), rect_r(ang)
    rings = []
    for (rad, w) in ((rr, -FT / 2), (hr, -FT / 2), (hr, FT / 2), (rr, FT / 2)):
        rings.append(Bk(uc + rad * np.cos(ang), vc + rad * np.sin(ang), w))
    V = np.vstack(rings); faces, fuv = [], []
    for k in range(4):
        k2 = (k + 1) % 4
        for j in range(NA):
            j2 = (j + 1) % NA
            fc = (k * NA + j, k * NA + j2, k2 * NA + j2, k2 * NA + j)
            faces.append(fc)
            fuv.append(tuple((V[i][0] / WOOD_TILE, (V[i][2] + V[i][1]) / WOOD_TILE) for i in fc))
    wood.add(V, faces, fuv)
    for w in (-FT / 2 - 0.0005, FT / 2 + 0.0005):
        ringp = Bk(uc + (hr + 0.0042) * np.cos(ang), vc + (hr + 0.0042) * np.sin(ang), w)
        tube(wood, np.vstack([ringp, ringp[:1]]), 0.0036, n=8, ref=(0, 1, 0))
    for sgn in (1, -1):
        tip_r = float(hole_r(np.array([pi / 2 * sgn % (2 * pi)]))[0])
        for w in (-FT / 2, FT / 2):
            ellipsoid(wood, Bk(uc, vc + sgn * (tip_r + 0.001), w), (0.0062, 0, 0), (0, 0.0062 * sin(RAKE), 0.0062), (0, 0.0042, 0), 10, 6)

# ---------------------------------------------------------------- lower back rail (arched)
ur = np.linspace(-0.183, 0.183, 33)
Pbr = Bk(ur, (V_BR0 + V_P0) / 2 + arch(ur), 0.0)
loft(wood, Pbr, lambda i: rrect(0.030, V_P0 - V_BR0 + 0.004, 0.006), ref=(0, 1, 0))

# ---------------------------------------------------------------- upholstered back panel (closed lens solid)
NS, NT = 40, 44
ss = np.linspace(-1, 1, NS); ts = np.linspace(0, 1, NT)
V, faces, fuv = [], [], []
Mring = 2 * NS
vmid = (V_P0 + V_P1) / 2
for t in ts:
    ring, ringuv = [], []
    for side, pad in ((-1, 0.020), (1, 0.009)):
        srange = ss if side == -1 else ss[::-1]
        for s in srange:
            v = V_P0 + (V_P1 - V_P0) * t
            hw = float(panel_hw(v)); u = s * hw
            vv = v + arch(u) * (1 - t)
            f = (1 - abs(s) ** 6) ** 0.5 * (1 - abs(2 * t - 1) ** 6) ** 0.5
            ring.append(Bk(u, vv, side * (0.004 + pad * f)))
            ringuv.append((0.5 + side * -1 * u / FAB_W, 0.8 + (vv - vmid) / FAB_H))
    V.append(ring); fuv.append(ringuv)
Vn = np.array(V).reshape(-1, 3)
idx = lambda i, j: i * Mring + (j % Mring)
ff, fu = [], []
for i in range(NT - 1):
    for j in range(Mring):
        if j == NS - 1 or j == Mring - 1:
            pass
        ff.append((idx(i, j), idx(i + 1, j), idx(i + 1, j + 1), idx(i, j + 1)))
        fu.append((fuv[i][j], fuv[i + 1][j], fuv[i + 1][(j + 1) % Mring], fuv[i][(j + 1) % Mring]))
for i in (0, NT - 1):
    ff.append(tuple(idx(i, j) for j in range(Mring)))
    fu.append(tuple(fuv[i][j] for j in range(Mring)))
fabric.add(Vn, ff, fu)

# ---------------------------------------------------------------- gimp trim (cord + scalloped loops), front and back
def trim_path():
    pts = []
    inset = 0.0075
    for u in np.linspace(-1, 1, 40):
        hw = float(panel_hw(V_P0)) - inset
        pts.append((u * hw, V_P0 + inset + arch(u * hw)))
    for v in np.linspace(V_P0 + inset, V_P1 - inset, 40)[1:]:
        pts.append((float(panel_hw(v)) - inset, v))
    for u in np.linspace(1, -1, 40)[1:]:
        pts.append((u * (float(panel_hw(V_P1)) - inset), V_P1 - inset))
    for v in np.linspace(V_P1 - inset, V_P0 + inset, 40)[1:-1]:
        pts.append((-(float(panel_hw(v)) - inset), v))
    return np.array(pts)
tp = trim_path()
ctr = np.array([0.0, (V_P0 + V_P1) / 2])
for side, wpos in ((-1, -0.0095), (1, 0.0095)):
    closed = np.vstack([tp, tp[:1]])
    P3 = Bk(closed[:, 0], closed[:, 1], wpos)
    # twisted two-ply cord
    seglen = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P3, axis=0), axis=1))])
    dense_s = np.arange(0, seglen[-1], 0.0022)
    D = np.stack([np.interp(dense_s, seglen, P3[:, k]) for k in range(3)], 1)
    D2 = np.stack([np.interp(dense_s, seglen, closed[:, k]) for k in range(2)], 1)
    for ply in (0, pi):
        tw = dense_s / 0.011 * 2 * pi + ply
        outdir = norm(D2 - ctr)
        off_u = outdir[:, 0] * np.cos(tw) * 0.0024
        off_v = outdir[:, 1] * np.cos(tw) * 0.0024
        Pc = Bk(D2[:, 0] + off_u, D2[:, 1] + off_v, wpos + side * 0.0015 + np.sin(tw) * 0.0024)
        tube(trim, Pc, 0.0027, n=6, tile=0.05, ref=(0, 1, 0))
    # scalloped loops pointing outward over the wood edge
    for s_ in np.arange(0, seglen[-1], 0.0108):
        p2 = np.array([np.interp(s_, seglen, closed[:, k]) for k in range(2)])
        p2b = np.array([np.interp(min(s_ + 0.002, seglen[-1]), seglen, closed[:, k]) for k in range(2)])
        tdir = norm(p2b - p2); odir = np.array([tdir[1], -tdir[0]])
        if np.dot(odir, p2 - ctr) < 0:
            odir = -odir
        la = np.linspace(-0.15 * pi, 1.15 * pi, 12)
        lu = p2[0] + tdir[0] * 0.0056 * np.cos(la) + odir[0] * (0.0025 + 0.0082 * np.sin(la))
        lv = p2[1] + tdir[1] * 0.0056 * np.cos(la) + odir[1] * (0.0025 + 0.0082 * np.sin(la))
        tube(trim, Bk(lu, lv, wpos + side * 0.0004 * np.sin(la)), 0.0013, n=5, tile=0.05, ref=(0, 1, 0))

# ---------------------------------------------------------------- seat frame
for sx in (1, -1):
    ys = np.linspace(0.235, -0.245, 9)
    P = np.array([(sx * (hw_seat(y) - 0.0125), y, 0.365) for y in ys])
    loft(wood, P, lambda i: rrect(0.070, 0.025, 0.004), ref=(0, 1, 0))
P = np.array([(x, 0.238, 0.365) for x in np.linspace(-0.18, 0.18, 5)])
loft(wood, P, lambda i: rrect(0.025, 0.070, 0.004), ref=(0, 1, 0))

xs = np.linspace(-0.248, 0.248, 61)
yfront = lambda x: -0.262 - 0.020 * (1 - (x / 0.248) ** 2)
zb = 0.343 - 0.011 * np.cos(2 * pi * xs / 0.36) * np.clip(1.25 - np.abs(xs) / 0.22, 0, 1)
P = np.array([(x, yfront(x) + 0.012, (0.40 + z) / 2) for x, z in zip(xs, zb)])
hh = 0.40 - zb
loft(wood, P, lambda i: rrect(0.024, hh[i], 0.004), ref=(0, 1, 0))
tube(wood, np.array([(x, yfront(x) - 0.0015, z + 0.0045) for x, z in zip(xs, zb)]), 0.0052, n=8, ref=(0, 0, 1))
tube(wood, np.array([(x, yfront(x) - 0.0008, 0.393) for x in xs]), 0.0038, n=8, ref=(0, 0, 1))

# corner blocks + turned front legs
LEG_X, LEG_Y = 0.238, -0.243
leg_ctrl = [(0.302, .0265), (0.296, .0305), (0.286, .0305), (0.280, .0215), (0.272, .0215), (0.266, .0285),
            (0.257, .0285), (0.251, .0205), (0.236, .0222), (0.170, .0268), (0.100, .0225), (0.066, .0185),
            (0.061, .0245), (0.051, .0245), (0.046, .0180), (0.036, .0180), (0.031, .0218), (0.008, .0195), (0.0, .0165)]
for sx in (1, -1):
    P = np.array([(sx * LEG_X, LEG_Y, z) for z in np.linspace(0.300, 0.400, 4)])
    loft(wood, P, lambda i: rrect(0.060, 0.060, 0.007), ref=(1, 0, 0))
    lathe(wood, smooth_profile(leg_ctrl, 5), (sx * LEG_X, LEG_Y, 0.0), axis=(0, 0, 1), seg=36)

# ---------------------------------------------------------------- arms, scroll knuckles, arm posts
KN_R, KN_W = 0.034, 0.058
for sx in (1, -1):
    ctrl = [(0.210, 0.300, 0.716), (0.228, 0.190, 0.737), (0.255, 0.030, 0.703), (0.277, -0.110, 0.668), (0.288, -0.205, 0.667)]
    P = catmull(ctrl, 12); P[:, 0] *= sx
    n = len(P)
    wid = np.linspace(0.042, 0.056, n)
    loft(wood, P, lambda i: rrect(wid[i], 0.031, 0.011, 6), ref=(1, 0, 0))
    for zoff, rad in ((-0.0035, 0.0034),):
        for side in (1, -1):
            Pb = P.copy(); Pb[:, 0] += side * (wid / 2 - 0.0008); Pb[:, 2] += zoff
            tube(wood, Pb[3:], rad, n=6, ref=(0, 0, 1))
    KC = np.array([sx * 0.288, -0.207, 0.667 + 0.0155 - KN_R])
    hw_ = KN_W / 2
    kprof = [(-hw_, 0.0), (-hw_, KN_R - 0.006), (-hw_ + 0.002, KN_R - 0.002), (-hw_ + 0.006, KN_R),
             (hw_ - 0.006, KN_R), (hw_ - 0.002, KN_R - 0.002), (hw_, KN_R - 0.006), (hw_, 0.0)]
    lathe(wood, kprof, KC, axis=(1, 0, 0), seg=40)
    for side in (1, -1):
        fc = KC + np.array([side * hw_, 0, 0])
        ph = np.linspace(0, 2 * pi * 1.6, 60); rho = np.linspace(0.027, 0.013, 60)
        Psp = np.stack([np.full(60, fc[0] + side * 0.0008), fc[1] + rho * np.cos(ph + 1.0), fc[2] + rho * np.sin(ph + 1.0)], 1)
        tube(wood, Psp, 0.0040 * np.sin(np.linspace(0.02, 0.98, 60) * pi) ** 0.35, n=8, ref=(1, 0, 0))
        ellipsoid(wood, fc, (side * 0.0075, 0, 0), (0, 0.0115, 0), (0, 0, 0.0115), 14, 7)
    ctrl = [(0.2685, -0.044, 0.676), (0.264, -0.074, 0.560), (0.258, -0.060, 0.450), (0.2555, -0.058, 0.370), (0.2555, -0.070, 0.305)]
    Pp = catmull(ctrl, 10); Pp[:, 0] *= sx
    n2 = len(Pp)
    dep = np.interp(np.linspace(0, 1, n2), [0, 0.5, 0.9, 1.0], [0.046, 0.054, 0.046, 0.042])
    thk = np.full(n2, 0.030)
    loft(wood, Pp, lambda i: rrect(thk[i], dep[i], min(0.008, thk[i] * 0.45)), ref=(1, 0, 0))

# ---------------------------------------------------------------- seat cushion
G = 72
sv = np.linspace(-1, 1, G)
Y_BACK = 0.205
V = np.zeros((G, G, 3)); UVc = np.zeros((G, G, 2))
for i, t in enumerate(sv):          # t: -1 front .. +1 back
    for j, s in enumerate(sv):
        m = max(abs(s), abs(t)); d6 = (abs(s) ** 6 + abs(t) ** 6) ** (1 / 6)
        k = m / d6 if d6 > 1e-9 else 1.0
        s2, t2 = s * k, t * k
        yf = -0.287 - 0.020 * (1 - s2 ** 2)
        y = yf + (Y_BACK - yf) * (t2 + 1) / 2
        x = s2 * (hw_seat(y) + 0.004)
        dd = min(1.0, m)
        z = SEAT_Z + 0.004 + 0.052 * (1 - dd ** 8) ** 0.42 + 0.046 * (1 - dd ** 2.2)
        V[i, j] = (x, y, z)
        drop = (SEAT_Z + 0.102) - z
        rad = norm(np.array([x, y + 0.04])) if (abs(x) + abs(y + 0.04)) > 1e-6 else np.zeros(2)
        ext = max(0.0, drop - 0.04) * 0.9
        UVc[i, j] = (0.5 + (x + rad[0] * ext) / FAB_W, 0.2 + (y + 0.04 + rad[1] * ext) / FAB_H)
faces, fuv = [], []
idx = lambda i, j: i * G + j
for i in range(G - 1):
    for j in range(G - 1):
        fc = (idx(i, j), idx(i, j + 1), idx(i + 1, j + 1), idx(i + 1, j))
        faces.append(fc); fuv.append(tuple(tuple(UVc[a // G, a % G]) for a in fc))
border = [idx(0, j) for j in range(G)] + [idx(i, G - 1) for i in range(1, G)] + \
         [idx(G - 1, j) for j in range(G - 2, -1, -1)] + [idx(i, 0) for i in range(G - 2, 0, -1)]
faces.append(tuple(reversed(border))); fuv.append(tuple(tuple(UVc[a // G, a % G]) for a in reversed(border)))
fabric.add(V.reshape(-1, 3), faces, fuv)

# ---------------------------------------------------------------- materials
def img(path, colorspace="sRGB"):
    im = bpy.data.images.load(str(path)); im.colorspace_settings.name = colorspace
    return im

def make_mat(name, albedo=None, normal=None, nstrength=1.0, **props):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes["Principled BSDF"]
    if albedo:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img(albedo)
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    if normal:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img(normal, "Non-Color")
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = nstrength
        nt.links.new(t.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    for k, val in props.items():
        b.inputs[k].default_value = val
    return m

bpy.ops.wm.read_factory_settings(use_empty=True)
m_wood = make_mat("Wood_Lacquer", TEX / "wood" / "wood_stained_albedo.jpg", TEX / "wood" / "wood_normal_1k.png", 0.35,
                  **{"Roughness": 0.34, "Coat Weight": 0.75, "Coat Roughness": 0.09, "Coat IOR": 1.5})
m_fab = make_mat("Fabric_Damask", TEX / "fabric" / "damask_albedo.jpg", TEX / "fabric" / "damask_normal.png", 1.2,
                 **{"Roughness": 0.88, "Sheen Weight": 0.55, "Sheen Roughness": 0.45, "Sheen Tint": (1.0, 0.95, 0.85, 1.0)})
m_trim = make_mat("Trim_Gimp", None, None,
                  **{"Base Color": (0.80, 0.72, 0.52, 1.0), "Roughness": 0.50, "Sheen Weight": 0.6, "Sheen Roughness": 0.35})

o_wood = wood.build("Chair_Wood", m_wood)
o_fab = fabric.build("Chair_Fabric", m_fab, sharp_deg=80)
o_trim = trim.build("Chair_Trim", m_trim, sharp_deg=80)

tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in (o_wood, o_fab, o_trim))
print("TRIS", tris, [len(o.data.polygons) for o in (o_wood, o_fab, o_trim)])
OUT.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "chair.blend"))
print("SAVED")
