"""Turn a downloaded glTF car into Test Drive 6 ready OBJ files (run inside Blender).

Usage (Blender 4.1+, from the game folder):
  blender -b --factory-startup --python tools/blender_car.py -- SRC.gltf OUTDIR \
      --scale 315 --wheels "0.83,-1.355,-0.135 0.83,1.645,-0.135" --radius 0.37 \
      [--wheel-width 0.14] [--hi 560] [--env 300] [--front -y]

  --wheels   wheel centres (model units, one per axle side; mirrored to -x automatically)
  --scale    game units per model unit (about 320 per metre matches the remaster cars)
  --front    model axis the car's nose points to (-y or +y; glTF imports +Z up)

Detailed models with many materials (interior, engine, separate wheels):
  --drop "INT_,ENG_,EXT_Rim"     delete faces whose material name starts with one of these
  --keep INT_Glass_Refl          never delete these (exceptions to --drop)
  --wheel-material EXT_Tyre      take wheel centres from these faces (one wheel per x/y
                                 quadrant) instead of --wheels, then delete them
  --bake 256                     build one new atlas texture: every material becomes a flat
                                 colour square (its texture's average colour), except...
  --detail Plate_D,EXT_Badges    ...these, which keep their texture detail (baked islands)
  --paint EXT_Car_Paint          these materials get the game's yellow paint mask colour
  --colour "EXT_Glass=35,45,55;HL_Glass=190,195,200"   flat colour (sRGB) for these materials

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

PAINT_MASK = (217, 184, 0)   # body colour of the remaster textures; the game tints it


def args():
    a = sys.argv[sys.argv.index("--") + 1:]
    opt = {"--scale": "315", "--radius": "0.37", "--wheel-width": "0.14", "--hi": "560",
           "--env": "300", "--front": "-y", "--wheels": "", "--drop": "", "--wheel-material": "",
           "--bake": "0", "--paint": "", "--colour": "", "--keep": "", "--detail": ""}
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
    colours = {}
    for item in filter(None, opt["--colour"].split(";")):
        name, rgb = item.split("=")
        colours[name.strip()] = tuple(int(c) for c in rgb.split(","))
    for name in filter(None, opt["--paint"].split(",")):
        colours[name.strip()] = PAINT_MASK
    # absolute paths: Blender resolves relative image/render paths against the .blend, not cwd
    return dict(src=os.path.abspath(pos[0]), out=os.path.abspath(pos[1]), scale=float(opt["--scale"]), wheels=wheels,
                radius=float(opt["--radius"]), width=float(opt["--wheel-width"]),
                hi=int(opt["--hi"]), env=int(opt["--env"]), front=opt["--front"],
                drop=[p for p in opt["--drop"].split(",") if p], wheel_mat=opt["--wheel-material"],
                keep=[p for p in opt["--keep"].split(",") if p],
                detail=[p for p in opt["--detail"].split(",") if p],
                bake=int(opt["--bake"]), colours=colours)


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


def material_ids(ob, prefixes):
    return {i for i, s in enumerate(ob.material_slots)
            if s.material and s.material.name.startswith(tuple(prefixes))}


def wheels_from_material(ob, prefix):
    """Wheel centres and radius from the faces of one material, one wheel per x/y quadrant."""
    ids = material_ids(ob, [prefix])
    quads = {}
    for p in ob.data.polygons:
        if p.material_index in ids:
            for vi in p.vertices:
                co = ob.data.vertices[vi].co
                q = quads.setdefault((co.x > 0, co.y > 0), [co.copy(), co.copy()])
                q[0] = mathutils.Vector([min(a, b) for a, b in zip(q[0], co)])
                q[1] = mathutils.Vector([max(a, b) for a, b in zip(q[1], co)])
    if len(quads) != 4:
        sys.exit(f"{prefix}: found {len(quads)} wheels, expected 4")
    centres = [tuple((lo + hi) / 2) for lo, hi in quads.values()]
    radius = sum((hi.z - lo.z) / 2 for lo, hi in quads.values()) / 4
    return centres, radius


def delete_materials(ob, prefixes, keep):
    ids = material_ids(ob, prefixes) - material_ids(ob, keep)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    doomed = [f for f in bm.faces if f.material_index in ids]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    # glTF splits vertices at UV seams and hard edges; weld them so decimation and the
    # atlas unwrap see connected surfaces (fewer cracks, fewer tiny UV islands)
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


def make_active(ob):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def srgb_to_linear(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return round(max(0.0, min(1.0, c)) * 255)


def flat_colour(mat, colours):
    """sRGB colour for a material drawn as one flat swatch: override, image average or base."""
    flat = next((rgb for name, rgb in colours.items() if mat.name.startswith(name)), None)
    if flat:
        return flat
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not bsdf:
        return (128, 128, 128)
    sock = bsdf.inputs["Base Color"]
    if not sock.links:
        return tuple(linear_to_srgb(c) for c in sock.default_value[:3])
    # follow the link back to an image and average its pixels (image pixels are sRGB here)
    stack, seen = [sock.links[0].from_node], set()
    while stack:
        node = stack.pop()
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.type == "TEX_IMAGE" and node.image and node.image.size[0]:
            px = node.image.pixels[:]
            n = len(px) // 4
            return tuple(round(sum(px[k::4]) / n * 255) for k in range(3))
        stack += [l.from_node for i in node.inputs for l in i.links]
    return (128, 128, 128)


SWATCH = 16   # flat colour squares per row in the bottom strip (2 rows, 1/16 of the height each)


def bake_atlas(ob, size, colours, detail, path):
    """New UV layer 'atlas': materials listed in detail get real islands (baked from their
    textures) in the top 7/8; every other material is one flat colour square in the bottom
    strip, as in the remaster textures (big flat paint area, small detail patches)."""
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    me = ob.data
    render_uv = me.uv_layers.active.name
    uv = me.uv_layers.new(name="atlas")
    me.uv_layers.active = uv          # bake target and export use the active layer
    for layer in me.uv_layers:
        layer.active_render = layer.name == render_uv   # texture lookups keep the old UVs
    detail_ids = material_ids(ob, detail)
    flat_ids = sorted({p.material_index for p in me.polygons} - detail_ids)   # used slots only
    if len(flat_ids) > 2 * SWATCH:
        sys.exit(f"{len(flat_ids)} flat materials, max {2 * SWATCH}")
    has_detail = any(p.material_index in detail_ids for p in me.polygons)
    if has_detail:
        for p in me.polygons:
            p.select = p.material_index in detail_ids
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(80), island_margin=0.01)
        bpy.ops.object.mode_set(mode="OBJECT")
    data = me.uv_layers["atlas"].data   # re-fetch: edit mode toggles invalidate old references
    swatch_of = {mid: k for k, mid in enumerate(flat_ids)}
    for p in me.polygons:
        for li in p.loop_indices:
            if p.material_index in detail_ids:
                u, v = data[li].uv
                data[li].uv = (u, 0.125 + v * 0.875)
            else:
                k = swatch_of[p.material_index]
                data[li].uv = ((k % SWATCH + 0.5) / SWATCH, (k // SWATCH + 0.5) / 16)
    work = size * 4                    # bake large, scale down for clean edges
    img = bpy.data.images.new("atlas", work, work)
    nodes_done = set()
    for slot in ob.material_slots:
        mat = slot.material
        if not mat or mat.name in nodes_done:
            continue
        nodes_done.add(mat.name)
        mat.use_nodes = True
        nt = mat.node_tree
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        em = nt.nodes.new("ShaderNodeEmission")
        bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf and bsdf.inputs["Base Color"].links:
            nt.links.new(bsdf.inputs["Base Color"].links[0].from_socket, em.inputs[0])
        elif bsdf:
            em.inputs[0].default_value = bsdf.inputs["Base Color"].default_value
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.nodes.active = tex
    if has_detail:
        sc = bpy.context.scene
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = 1
        make_active(ob)
        bpy.ops.object.bake(type="EMIT", margin=16, use_clear=True)
    # paint the flat squares over the bottom strip (image pixels are sRGB floats, bottom row first)
    px = list(img.pixels[:])
    cell = work // SWATCH
    for mid, k in swatch_of.items():
        mat = ob.material_slots[mid].material
        rgb = flat_colour(mat, colours) if mat else (128, 128, 128)
        x0, y0 = (k % SWATCH) * cell, (k // SWATCH) * cell
        for y in range(y0, y0 + cell):
            row = (y * work + x0) * 4
            for x in range(cell):
                px[row + 4 * x:row + 4 * x + 4] = [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 1.0]
    img.pixels[:] = px
    img.filepath_raw = path.replace(".png", f"_{work}.png")
    img.file_format = "PNG"
    img.save()
    small = img.copy()
    small.scale(size, size)
    small.filepath_raw = path
    small.file_format = "PNG"
    small.save()
    # show the atlas in the preview: emission from the baked image through the atlas UVs
    for mat_name in nodes_done:
        nt = bpy.data.materials[mat_name].node_tree
        tex = nt.nodes.active
        uvn = nt.nodes.new("ShaderNodeUVMap")
        uvn.uv_map = "atlas"
        nt.links.new(uvn.outputs[0], tex.inputs[0])


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
    a = args()
    os.makedirs(a["out"], exist_ok=True)
    ob = load_joined(a["src"])
    wheels, radius, removed = a["wheels"], a["radius"], 0
    if a["wheel_mat"]:
        wheels, radius = wheels_from_material(ob, a["wheel_mat"])
        a["drop"].append(a["wheel_mat"])
    if a["drop"]:
        removed += delete_materials(ob, a["drop"], a["keep"])
    if a["wheels"]:
        removed += remove_wheels(ob, wheels, radius, a["width"])
    lo = mathutils.Vector([min(v.co[k] for v in ob.data.vertices) for k in range(3)])
    hi = mathutils.Vector([max(v.co[k] for v in ob.data.vertices) for k in range(3)])
    centre = (lo + hi) / 2
    make_active(ob)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    hi_ob = lod(ob, a["hi"], "hi")
    tex_path = os.path.join(a["out"], "texture.png")
    if a["bake"]:
        make_active(hi_ob)
        bake_atlas(hi_ob, a["bake"], a["colours"], a["detail"], tex_path)
        tex = "baked atlas"
        env_ob = lod(hi_ob, a["env"], "env")
    else:
        env_ob = lod(ob, a["env"], "env")
        tex = save_texture(ob, tex_path)
    n_hi = export(hi_ob, os.path.join(a["out"], "hi.obj"), centre, a["scale"], a["front"])
    n_env = export(env_ob, os.path.join(a["out"], "env.obj"), centre, a["scale"], a["front"])
    scale, flip = a["scale"], -1 if a["front"] == "-y" else 1
    with open(os.path.join(a["out"], "info.txt"), "w") as f:
        f.write(f"faces removed: {removed}\nhi triangles: {n_hi}\nenv triangles: {n_env}\n")
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
        f.write(f"wheel radius (game units): {radius * scale:.0f}\n")
    preview(hi_ob, os.path.join(a["out"], "preview.png"))
    print("RESULT done", n_hi, n_env, removed)


main()
