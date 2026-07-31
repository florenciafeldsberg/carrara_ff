import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import math

TOL = sc.doc.ModelAbsoluteTolerance
ANGLE_STEP_DEG = 5

def build_angle_list(step_deg):
    n = int(round(360.0 / step_deg))
    print("build_angle_list: step_deg={}, n={}".format(step_deg, n))
    result = [i * step_deg for i in range(n)]
    print("build_angle_list: result={}".format(result))
    return result

def get_geometry_by_layer(layer_name):
    prev_doc = sc.doc
    print("get_geometry_by_layer: prev_doc={}".format(prev_doc))
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    print("get_geometry_by_layer: sc.doc swappe3d to ActiveDoc={}".format(sc.doc))
    try:
        doc = sc.doc
        layer_index = doc.Layers.FindByFullPath(layer_name, True)
        print("layer_name recibido: {!r}".format(layer_name))
        print("layer_index encontrado: {}".format(layer_index))
        print("TOTAL objetos en el documento de Rhino: {}".format(doc.Objects.Count))
        layer_paths_presentes = set()
        for obj in doc.Objects:
            layer_paths_presentes.add(doc.Layers[obj.Attributes.LayerIndex].FullPath)
        print("Layers que SI tienen objetos: {}".format(sorted(layer_paths_presentes)))
        if layer_index < 0:
            print("No se encontro la layer, devolviendo lista vacia")
            return []
        breps = []
        objs_en_layer = 0
        for obj_i, obj in enumerate(doc.Objects):
            if obj.Attributes.LayerIndex != layer_index:
                continue
            objs_en_layer += 1
            geo = obj.Geometry
            print("get_geometry_by_layer: obj {} en layer, tipo geo={}".format(obj_i, type(geo).__name__))
            brep = geo if isinstance(geo, rg.Brep) else rg.Brep.TryConvertBrep(geo)
            print("get_geometry_by_layer: obj {} conversion a Brep -> {}".format(obj_i, "OK" if brep else "FALLO"))
            if brep:
                breps.append(brep)
        print("objetos en la layer: {}, convertidos a Brep: {}".format(objs_en_layer, len(breps)))
        return breps
    finally:
        sc.doc = prev_doc
        print("get_geometry_by_layer: sc.doc restaurado a {}".format(sc.doc))

def union_bbox(breps):
    bbox = rg.BoundingBox.Empty
    for i, b in enumerate(breps):
        b_bbox = b.GetBoundingBox(True)
        print("union_bbox: brep {} bbox min={}, max={}".format(i, b_bbox.Min, b_bbox.Max))
        bbox.Union(b_bbox)
        print("union_bbox: acumulado tras brep {} -> min={}, max={}".format(i, bbox.Min, bbox.Max))
    return bbox

def move_to_origin(breps, corner_pt):
    xf = rg.Transform.Translation(rg.Point3d.Origin - corner_pt)
    print("move_to_origin: corner_pt={}, xf={}".format(corner_pt, xf))
    moved = []
    for i, b in enumerate(breps):
        b2 = b.Duplicate()
        b2.Transform(xf)
        print("move_to_origin: brep {} duplicado y transformado, nueva bbox min={}".format(i, b2.GetBoundingBox(True).Min))
        moved.append(b2)
    print("move_to_origin: total movidos={}".format(len(moved)))
    return moved

def make_cutting_planes(angles_deg, origin=rg.Point3d.Origin, axis=rg.Vector3d.ZAxis):
    base_plane = rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.ZAxis)
    print("make_cutting_planes: base_plane origin={}, xaxis={}, yaxis={}".format(base_plane.Origin, base_plane.XAxis, base_plane.YAxis))
    planes = []
    for a in angles_deg:
        pl = rg.Plane(base_plane)
        rot = rg.Transform.Rotation(math.radians(a), axis, origin)
        pl.Transform(rot)
        print("make_cutting_planes: angulo={} -> plane origin={}, normal={}".format(a, pl.Origin, pl.Normal))
        planes.append(pl)
    print("make_cutting_planes: total planos generados={}".format(len(planes)))
    return planes

def slice_by_angles(breps, angles_deg):
    planes = make_cutting_planes(angles_deg)
    # Cierra el círculo de ángulos para armar pares consecutivos
    plane_pairs = list(zip(planes, planes[1:] + [planes[0]]))
    print("angles_deg: {}, cantidad de pares de planos: {}".format(angles_deg, len(plane_pairs)))

    pieces = []
    for bi, b in enumerate(breps):
        for pair_i, (p1, p2) in enumerate(plane_pairs):
            piece = b
            for pl_i, (pl, keep_positive) in enumerate([(p1, True), (p2, False)]):
                cutter = rg.PlaneSurface(
                    pl,
                    rg.Interval(-1e6, 1e6),
                    rg.Interval(-1e6, 1e6)
                ).ToBrep()
                print("brep {} par {} plano {}: cutter creado, keep_positive={}".format(bi, pair_i, pl_i, keep_positive))
                trim_plane = pl if keep_positive else rg.Plane(pl.Origin, -pl.Normal)
                trimmed = piece.Trim(trim_plane, TOL)
                print("brep {} par {} plano {}: Trim devolvio {} resultado(s)".format(bi, pair_i, pl_i, len(trimmed) if trimmed else 0))
                if trimmed:
                    piece = trimmed[0]
                    print("brep {} par {} plano {}: piece actualizado, bbox min={}".format(bi, pair_i, pl_i, piece.GetBoundingBox(True).Min))
                else:
                    print("brep {} par {}: Trim devolvio vacio, se mantiene el piece anterior sin recortar por este plano".format(bi, pair_i))
            if piece:
                pieces.append(piece)
                print("brep {} par {}: piece final agregado a pieces (total actual={})".format(bi, pair_i, len(pieces)))
    print("piezas totales generadas por slice_by_angles: {}".format(len(pieces)))
    return pieces

def name_pieces(pieces, layer_name):
    names = ["{}_{:02d}".format(layer_name, i) for i in range(len(pieces))]
    print("name_pieces: layer_name={}, names generados={}".format(layer_name, names))
    return names

def recenter_each(pieces):
    recentered = []
    for i, p in enumerate(pieces):
        bbox = p.GetBoundingBox(True)
        print("recenter_each: piece {} bbox min antes={}".format(i, bbox.Min))
        xf = rg.Transform.Translation(rg.Point3d.Origin - bbox.Min)
        p2 = p.Duplicate()
        p2.Transform(xf)
        print("recenter_each: piece {} recentrado, bbox min despues={}".format(i, p2.GetBoundingBox(True).Min))
        recentered.append(p2)
    print("recenter_each: total recentrados={}".format(len(recentered)))
    return recentered

def piece_bboxes(pieces):
    boxes = [rg.Box(p.GetBoundingBox(True)) for p in pieces]
    for i, box in enumerate(boxes):
        print("piece_bboxes: piece {} box={}".format(i, box))
    print("piece_bboxes: total boxes={}".format(len(boxes)))
    return boxes

print("=== inicio run ===")

raw_breps = get_geometry_by_layer(layer_name)
print("raw_breps: {}".format(len(raw_breps)))

if raw_breps:
    bbox = union_bbox(raw_breps)
    print("bbox union min: {}, max: {}".format(bbox.Min, bbox.Max))
    aligned_breps = move_to_origin(raw_breps, bbox.Min)
    print("aligned_breps: {}".format(len(aligned_breps)))
    angles_deg = build_angle_list(ANGLE_STEP_DEG)
    print("angles_deg (hardcoded, paso {}): {}".format(ANGLE_STEP_DEG, angles_deg))
    pieces = slice_by_angles(aligned_breps, angles_deg)
    names_out = name_pieces(pieces, layer_name)
    geo_out = recenter_each(pieces)
    bbox_out = piece_bboxes(geo_out)
    print("geo_out final: {}, names_out final: {}, bbox_out final: {}".format(len(geo_out), len(names_out), len(bbox_out)))
else:
    print("raw_breps vacio -> geo_out y names_out van a quedar vacios")
    geo_out = []
    names_out = []
    bbox_out = []
print("=== fin run ===")