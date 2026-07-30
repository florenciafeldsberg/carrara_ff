"""
GHPython component
Inputs:
    layer_name : str          -> nombre de la layer a procesar
    angles     : list[float]  -> ángulos de corte en grados (ej: [0, 45, 90, 180])
Outputs:
    geo_out    : list[Brep]   -> piezas finales, cada una movida a su propio 0,0,0
    names_out  : list[str]    -> obj_name de cada pieza, en el mismo orden
"""

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import math

TOL = sc.doc.ModelAbsoluteTolerance

def get_geometry_by_layer(layer_name):
    prev_doc = sc.doc
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    try:
        doc = sc.doc
        layer_index = doc.Layers.FindByFullPath(layer_name, True)
        print("layer_name recibido: {!r}".format(layer_name))
        print("layer_index encontrado: {}".format(layer_index))
        if layer_index < 0:
            print("No se encontro la layer, devolviendo lista vacia")
            return []
        breps = []
        objs_en_layer = 0
        for obj in doc.Objects:
            if obj.Attributes.LayerIndex != layer_index:
                continue
            objs_en_layer += 1
            geo = obj.Geometry
            brep = geo if isinstance(geo, rg.Brep) else rg.Brep.TryConvertBrep(geo)
            if brep:
                breps.append(brep)
        print("objetos en la layer: {}, convertidos a Brep: {}".format(objs_en_layer, len(breps)))
        return breps
    finally:
        sc.doc = prev_doc

def union_bbox(breps):
    bbox = rg.BoundingBox.Empty
    for b in breps:
        bbox.Union(b.GetBoundingBox(True))
    return bbox


def move_to_origin(breps, corner_pt):
    xf = rg.Transform.Translation(rg.Point3d.Origin - corner_pt)
    moved = []
    for b in breps:
        b2 = b.Duplicate()
        b2.Transform(xf)
        moved.append(b2)
    return moved


def make_cutting_planes(angles_deg, origin=rg.Point3d.Origin, axis=rg.Vector3d.ZAxis):
    base_plane = rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    planes = []
    for a in angles_deg:
        pl = rg.Plane(base_plane)
        rot = rg.Transform.Rotation(math.radians(a), axis, origin)
        pl.Transform(rot)
        planes.append(pl)
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
            for pl, keep_positive in [(p1, True), (p2, False)]:
                cutter = rg.PlaneSurface(
                    pl,
                    rg.Interval(-1e6, 1e6),
                    rg.Interval(-1e6, 1e6)
                ).ToBrep()
                trimmed = piece.Trim(pl if keep_positive else rg.Plane(pl.Origin, -pl.Normal), TOL)
                if trimmed:
                    piece = trimmed[0]
                else:
                    print("brep {} par {}: Trim devolvio vacio, se mantiene el piece anterior sin recortar por este plano".format(bi, pair_i))
            if piece:
                pieces.append(piece)
    print("piezas totales generadas por slice_by_angles: {}".format(len(pieces)))
    return pieces


def name_pieces(pieces, layer_name):
    return ["{}_{:02d}".format(layer_name, i) for i in range(len(pieces))]


def recenter_each(pieces):
    recentered = []
    for p in pieces:
        bbox = p.GetBoundingBox(True)
        xf = rg.Transform.Translation(rg.Point3d.Origin - bbox.Min)
        p2 = p.Duplicate()
        p2.Transform(xf)
        recentered.append(p2)
    return recentered


print("=== inicio run ===")
print("angles input: {}".format(angles))

raw_breps = get_geometry_by_layer(layer_name)
print("raw_breps: {}".format(len(raw_breps)))

if raw_breps:
    bbox = union_bbox(raw_breps)
    print("bbox union min: {}, max: {}".format(bbox.Min, bbox.Max))
    aligned_breps = move_to_origin(raw_breps, bbox.Min)
    pieces = slice_by_angles(aligned_breps, angles)
    names_out = name_pieces(pieces, layer_name)
    geo_out = recenter_each(pieces)
    print("geo_out final: {}, names_out final: {}".format(len(geo_out), len(names_out)))
else:
    print("raw_breps vacio -> geo_out y names_out van a quedar vacios")
    geo_out = []
    names_out = []
print("=== fin run ===")