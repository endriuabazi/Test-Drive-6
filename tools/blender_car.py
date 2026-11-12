"""Turn a downloaded glTF car into Test Drive 6 ready OBJ files (run inside Blender).

Usage (Blender 4.1+, from the game folder):
  blender -b --factory-startup --python tools/blender_car.py -- SRC.gltf OUTDIR \
      --scale 315 --wheels "0.83,-1.355,-0.135 0.83,1.645,-0.135" --radius 0.37 \
      [--wheel-width 0.14] [--hi 560] [--env 300] [--front -y]

  --wheels   wheel centres (model units, one per axle side; mirrored to -x automatically)
  --scale    game units per model unit
  --front    model axis the car's nose points to (-y or +y; glTF imports +Z up)

Writes to OUTDIR: hi.obj and env.obj (game coordinates: +X right, +Y up, +Z front, centred
on the body's bounding box, triangle order as in the retail models), texture.png (256x256),
info.txt (wheel centres and size in game units) and preview.png.
Wheels are removed: the game draws its own (hubs archive, WHEEL_CENTRES in the .scr).
"""
import math
import os
import sys

import bmesh
import bpy
import mathutils


def args():
    a = sys.argv[sys.argv.index("--") + 1:]
    opt = {"--scale": "315", "--radius": "0.37", "--wheel-width": "0.14", "--hi": "560",
           "--env": "300", "--front": "-y", "--wheels": ""}
    pos = []
    i = 0
    while i < len(a):
        if a[i] in opt:
            opt[a[i]] = a[i + 1]
            i += 2
        else:
            pos.append(a[i])
            i += 1
    if len(pos) != 2:
        sys.exit(__doc__)
    wheels = []
    for w in opt["--wheels"].split():
        x, y, z = map(float, w.split(","))
        wheels += [(abs(x), y, z), (-abs(x), y, z)]
    return pos[0], pos[1], float(opt["--scale"]), wheels, float(opt["--radius"]), \
        float(opt["--wheel-width"]), int(opt["--hi"]), int(opt["--env"]), opt["--front"]


def load_joined(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    # glTF files usually carry a scaled root node; bake the full world matrix into the mesh
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


def remove_wheels(ob, wheels, radius, width):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    seen, doomed = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        part, stack = [], [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            part.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        vs = {v for g in part for v in g.verts}
        for cx, cy, cz in wheels:
            if all(abs(v.co.x - cx) <= width and abs(v.co.y - cy) <= radius
                   and abs(v.co.z - cz) <= radius for v in vs):
                doomed += part
                break
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(ob.data)
    bm.free()
    return len(doomed)


def lod(ob, tris, name):
    cur = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    copy = ob.copy()
    copy.data = ob.data.copy()
    copy.name = name
    bpy.context.scene.collection.objects.link(copy)
    m = copy.modifiers.new("dec", "DECIMATE")
    m.ratio = min(1.0, tris / cur)
    m.use_symmetry = True
    m.symmetry_axis = "X"
    m.use_collapse_triangulate = True
    copy.modifiers.new("tri", "TRIANGULATE")
    return copy


def export(ob, path, centre, scale, front):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    uvl = me.uv_layers.active.data
    normals = me.corner_normals
    flip = -1 if front == "-y" else 1   # nose direction in Blender is flip * Y

    def g(p):
        # Blender (right-handed, Z up) -> game (left-handed, +Y up, +Z front, +X right):
        # front = flip*Y, up = Z, right = front x up = flip*X
        p = p - centre
        return (flip * p.x * scale, p.z * scale, flip * p.y * scale)

    def gn(n):
        return (flip * n.x, n.z, flip * n.y)

    vs, vts, vns, faces = [], [], [], []
    for t in me.loop_triangles:
        corner = []
        for li in t.loops:
            vs.append(g(me.vertices[me.loops[li].vertex_index].co))
            vns.append(gn(normals[li].vector))
            vts.append(tuple(uvl[li].uv))
            corner.append(len(vs))
        # the mapping is a mirror (det -1) for either nose direction, which turns Blender's
        # outward CCW order into the retail order (cross(b-a, c-a) opposite the normal)
        faces.append(corner)
    with open(path, "w") as f:
        f.write(f"# {len(faces)} triangles\n")
        f.writelines(f"v {x:.4f} {y:.4f} {z:.4f}\n" for x, y, z in vs)
        f.writelines(f"vt {u:.6f} {v:.6f}\n" for u, v in vts)
        f.writelines(f"vn {x:.5f} {y:.5f} {z:.5f}\n" for x, y, z in vns)
        f.writelines(f"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n" for a, b, c in faces)
    ev.to_mesh_clear()
    return len(faces)


def save_texture(ob, path):
    for mat in ob.data.materials:
        for node in mat.node_tree.nodes if mat and mat.node_tree else []:
            if node.type == "TEX_IMAGE" and node.image:
                img = node.image.copy()
                img.scale(256, 256)
                img.filepath_raw = path
                img.file_format = "PNG"
                img.save()
                return node.image.name
    return None


def preview(obj, path):
    for o in bpy.context.scene.objects:
        o.hide_render = o is not obj
    lo, hi = [mathutils.Vector(v) for v in (obj.bound_box[0], obj.bound_box[6])]
    c, r = (lo + hi) / 2, (hi - lo).length
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = c + mathutils.Vector((r * 0.8, -r * 0.9, r * 0.45))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.color_type = "TEXTURE"
    sc.render.resolution_x, sc.render.resolution_y = 900, 500
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    src, out, scale, wheels, radius, width, hi_tris, env_tris, front = args()
    os.makedirs(out, exist_ok=True)
    ob = load_joined(src)
    removed = remove_wheels(ob, wheels, radius, width)
    lo = mathutils.Vector([min(v.co[k] for v in ob.data.vertices) for k in range(3)])
    hi = mathutils.Vector([max(v.co[k] for v in ob.data.vertices) for k in range(3)])
    centre = (lo + hi) / 2
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    hi_ob, env_ob = lod(ob, hi_tris, "hi"), lod(ob, env_tris, "env")
    n_hi = export(hi_ob, os.path.join(out, "hi.obj"), centre, scale, front)
    n_env = export(env_ob, os.path.join(out, "env.obj"), centre, scale, front)
    tex = save_texture(ob, os.path.join(out, "texture.png"))
    flip = -1 if front == "-y" else 1
    with open(os.path.join(out, "info.txt"), "w") as f:
        f.write(f"wheel faces removed: {removed}\nhi triangles: {n_hi}\nenv triangles: {n_env}\n")
        f.write(f"texture: {tex}\nscale: {scale}\n")
        size = (hi - lo) * scale
        f.write(f"size (game units) x {size.x:.0f} y {size.z:.0f} z {size.y:.0f}\n")
        game = []
        for w in wheels:
            p = mathutils.Vector(w) - centre
            game.append((flip * p.x * scale, p.z * scale, flip * p.y * scale))
        # retail order: front left, front right, rear left, rear right
        for k, (x, y, z) in enumerate(sorted(game, key=lambda w: (-w[2], w[0]))):
            f.write(f"WHEEL_CENTRES{k}:{{{x:.0f},{y:.0f},{z:.0f}}}\n")
        f.write(f"wheel arch radius (game units): {radius * scale:.0f}\n")
    preview(hi_ob, os.path.join(out, "preview.png"))
    print("RESULT done", n_hi, n_env, removed)


main()
