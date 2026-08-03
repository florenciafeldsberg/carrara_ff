# libraries
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import math

# tools
def get_geometry_by_layer(layer_name):
    prev_doc = sc.doc
    sc.doc = Rhino.RhinoDoc.ActiveDoc
    try:
        doc = sc.doc
        layer_index = doc.Layers.FindByFullPath(layer_name, True)
        #print("layer_name recibido: {!r}".format(layer_name))
        #print("layer_index encontrado: {}".format(layer_index))

        settings = Rhino.DocObjects.ObjectEnumeratorSettings()
        settings.HiddenObjects = True
        settings.LockedObjects = True
        settings.NormalObjects = True

        found = []
        for obj in doc.Objects.GetObjectList(settings):
            if obj.Attributes.LayerIndex == layer_index:
                geo = obj.Geometry
                if isinstance(geo, rg.Brep):
                    found.append(geo)

        #print("objetos encontrados en la layer: {}".format(len(found)))

        return found
    finally:
        sc.doc = prev_doc

def get_bbox(geo_list):
    bbox = rg.BoundingBox.Empty
    for g in geo_list:
        bbox.Union(g.GetBoundingBox(True))
    #print("bbox min = {}, max ={}".format(bbox.Min, bbox.Max))
    return bbox

def bbox_to_brep(bbox):
    box = rg.Box(bbox)
    brep = box.ToBrep()
    #print("bbox convertido a brep: {}".format(brep))
    return brep

def move_center_to_xy_origin(geo_list, bbox):
    a = bbox.Center
    p = rg.Point3d(0, 0, a.Z)
    xf = rg.Transform.Translation(p - a)
    #print("moviendo centro A = {} a P = {}".format(a, p))

    moved = []
    for g in geo_list:
        g2 = g.Duplicate()
        g2.Transform(xf)
        moved.append(g2)

    return moved

def make_cutting_plane(angle_deg, origin=rg.Point3d.Origin, axis=rg.Vector3d.ZAxis):
    pl = rg.Plane(origin, rg.Vector3d.XAxis, rg.Vector3d.ZAxis)
    rot = rg.Transform.Rotation(math.radians(angle_deg), axis, origin)
    pl.Transform(rot)
    #print("plano de corte: angulo={}, origin={}, normal={}".format(angle_deg, pl.Origin, pl.Normal))
    return pl

def build_angle_list(step_deg):
    n = int(round(360.0 / step_deg))
    angles = [i * step_deg for i in range(n)]
    #print("build_angle_list: step_deg={}, angles={}".format(step_deg, angles))
    return angles

def split_by_angle(geo, step_deg):
    angles = build_angle_list(step_deg)
    planes = [make_cutting_plane(a) for a in angles]
    plane_pairs = list(zip(planes, planes[1:] + [planes[0]]))
    #print("split_by_angle: cantidad de pares de planos={}".format(len(plane_pairs)))

    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance

    wedges = []
    for pair_i, (p1, p2) in enumerate(plane_pairs):
        piece = geo
        for pl, keep_positive in [(p1, True), (p2, False)]:
            trim_plane = pl if keep_positive else rg.Plane(pl.Origin, -pl.Normal)
            trimmed = piece.Trim(trim_plane, tol)
            if trimmed:
                piece = trimmed[0]
            else:
                piece = None
                #print("split_by_angle: par {} sin interseccion, se descarta".format(pair_i))
                break
        if piece:
            wedges.append(piece)
            #print("split_by_angle: par {} -> pieza agregada (total={})".format(pair_i, len(wedges)))

    #print("split_by_angle: total piezas generadas={}".format(len(wedges)))
    return wedges

def recenter_by_centroid(pieces):
    recentered = []
    for i, p in enumerate(pieces):
        vmp = rg.VolumeMassProperties.Compute(p)
        centroid = vmp.Centroid
        target = rg.Point3d(0, 0, centroid.Z)
        #print("recenter_by_centroid: pieza {} centroide={}, target={}".format(i, centroid, target))

        xf = rg.Transform.Translation(target - centroid)
        p2 = p.Duplicate()
        p2.Transform(xf)
        #print("recenter_by_centroid: pieza {} tipo={}, valido={}".format(i, type(p2).__name__, p2.IsValid))
        recentered.append(p2)

    #print("recenter_by_centroid: total recentrados={}".format(len(recentered)))
    return recentered

def cap_pieces(pieces):
    tol = Rhino.RhinoDoc.ActiveDoc.ModelAbsoluteTolerance
    capped = []
    cap_face_indices = []
    for i, p in enumerate(pieces):
        n_naked_before = len([e for e in p.Edges if e.Valence == rg.EdgeAdjacency.Naked])
        n_faces_before = p.Faces.Count
        #print("cap_pieces: pieza {} ANTES -> IsSolid={}, naked_edges={}, faces={}".format(i, p.IsSolid, n_naked_before, n_faces_before))

        capped_p = p.CapPlanarHoles(tol)
        if capped_p:
            n_naked_after = len([e for e in capped_p.Edges if e.Valence == rg.EdgeAdjacency.Naked])
            n_faces_after = capped_p.Faces.Count
            cap_face_index = n_faces_before if n_faces_after > n_faces_before else None
            #print("cap_pieces: pieza {} DESPUES -> IsSolid={}, naked_edges={}, faces={}, cap_face_index={}".format(i, capped_p.IsSolid, n_naked_after, n_faces_after, cap_face_index))
            capped.append(capped_p)
            cap_face_indices.append(cap_face_index)
        else:
            #print("cap_pieces: pieza {} CapPlanarHoles devolvio None, se mantiene sin cappear".format(i))
            capped.append(p)
            cap_face_indices.append(None)

    #print("cap_pieces: total piezas={}".format(len(capped)))
    return capped, cap_face_indices

def orient_pieces_to_xy(pieces, cap_face_indices):
    oriented = []
    for i, p in enumerate(pieces):
        face_i = cap_face_indices[i]
        if face_i is None:
            #print("orient_pieces_to_xy: pieza {} sin cara cap identificada, se mantiene sin rotar".format(i))
            oriented.append(p)
            continue

        face = p.Faces[face_i]
        success, plane = face.TryGetPlane()
        if not success:
            #print("orient_pieces_to_xy: pieza {} no se pudo obtener el plano de la cara cap".format(i))
            oriented.append(p)
            continue

        amp = rg.AreaMassProperties.Compute(face)
        plane.Origin = amp.Centroid
        #print("orient_pieces_to_xy: pieza {} plano cap origin={}, normal={}".format(i, plane.Origin, plane.Normal))

        xf = rg.Transform.PlaneToPlane(plane, rg.Plane.WorldXY)
        p2 = p.Duplicate()
        p2.Transform(xf)
        oriented.append(p2)

    #print("orient_pieces_to_xy: total orientados={}".format(len(oriented)))
    return oriented

def explode_and_flatten(pieces, piece_prefix):
    planar_pieces = []
    labels = []

    for i, p in enumerate(pieces):
        piece_label = "{}{:02d}".format(piece_prefix, i + 1)
        bbox = p.GetBoundingBox(True)
        mid_z = (bbox.Min.Z + bbox.Max.Z) / 2.0

        side_count = 0
        for f in p.Faces:
            face_brep = f.DuplicateFace(False)
            success, plane = f.TryGetPlane()

            if not success:
                #print("explode_and_flatten: {} cara {} es curva, se omite por ahora".format(piece_label, f.FaceIndex))
                continue

            amp = rg.AreaMassProperties.Compute(face_brep)
            centroid = amp.Centroid

            if abs(plane.Normal.Z) > 0.9:
                face_type = "top" if centroid.Z > mid_z else "bottom"
            else:
                side_count += 1
                face_type = "side{}".format(side_count)

            face_label = "{}_{}".format(piece_label, face_type)

            plane.Origin = centroid
            xf = rg.Transform.PlaneToPlane(plane, rg.Plane.WorldXY)
            flat_face = face_brep.Duplicate()
            flat_face.Transform(xf)

            #print("explode_and_flatten: {} -> tipo={}".format(face_label, face_type))

            planar_pieces.append(flat_face)
            labels.append(face_label)

    #print("explode_and_flatten: total caras planas={}".format(len(planar_pieces)))
    return planar_pieces, labels

def build_axo_wireframe(pieces, piece_prefix):
    xf_z = rg.Transform.Rotation(math.radians(45.0), rg.Vector3d.ZAxis, rg.Point3d.Origin)
    xf_x = rg.Transform.Rotation(math.radians(35.264), rg.Vector3d.XAxis, rg.Point3d.Origin)

    axo_edges_list = []
    axo_labels = []

    for i, p in enumerate(pieces):
        piece_label = "{}{:02d}".format(piece_prefix, i + 1)
        axo_label = "{}_axo".format(piece_label)

        edges_2d = []
        for edge in p.Edges:
            success, polyline = edge.TryGetPolyline()
            if success:
                pts = list(polyline)
            else:
                params = edge.DivideByCount(16, True)
                pts = [edge.PointAt(t) for t in params] if params else []

            projected = []
            for pt in pts:
                pt2 = rg.Point3d(pt)
                pt2.Transform(xf_z)
                pt2.Transform(xf_x)
                projected.append([pt2.X, pt2.Y])

            if projected:
                edges_2d.append(projected)

        #print("build_axo_wireframe: {} -> {} aristas".format(axo_label, len(edges_2d)))

        axo_edges_list.append(edges_2d)
        axo_labels.append(axo_label)

    #print("build_axo_wireframe: total axos={}".format(len(axo_edges_list)))
    return axo_edges_list, axo_labels

def piece_bboxes(pieces):
    boxes = []
    for i, p in enumerate(pieces):
        bbox = p.GetBoundingBox(True)
        size = bbox.Max - bbox.Min
        #print("piece_bboxes: pieza {} min={}, max={}, size={}".format(i, bbox.Min, bbox.Max, size))
        boxes.append(bbox)

    #print("piece_bboxes: total bboxes={}".format(len(boxes)))
    return boxes

def print_biggest_bbox(boxes):
    biggest_i = -1
    biggest_diag = -1
    for i, bbox in enumerate(boxes):
        size = bbox.Max - bbox.Min
        diag = size.Length
        if diag > biggest_diag:
            biggest_diag = diag
            biggest_i = i

    biggest_bbox = boxes[biggest_i]
    size = biggest_bbox.Max - biggest_bbox.Min
    #print("bbox mas grande: pieza {}, min={}, max={}, size={}".format(biggest_i, biggest_bbox.Min, biggest_bbox.Max, size))
    return biggest_bbox

# main
def main(layer_name, angle, piece_prefix):
    raw_objs = get_geometry_by_layer(layer_name)
    bbox = get_bbox(raw_objs)
    bbox_brep = bbox_to_brep(bbox)
    moved_objs = move_center_to_xy_origin(raw_objs, bbox)

    split_pieces = split_by_angle(moved_objs[0], angle)
    recentered_pieces = recenter_by_centroid(split_pieces)
    capped_pieces, cap_face_indices = cap_pieces(recentered_pieces)
    oriented_pieces = orient_pieces_to_xy(capped_pieces, cap_face_indices)
    planar_pieces, labels = explode_and_flatten(oriented_pieces, piece_prefix)
    axo_edges_list, axo_labels = build_axo_wireframe(oriented_pieces, piece_prefix)

    piece_boxes = piece_bboxes(oriented_pieces)
    biggest_bbox = print_biggest_bbox(piece_boxes)

    return (moved_objs, bbox_brep, split_pieces, recentered_pieces, capped_pieces, oriented_pieces,
            planar_pieces, labels, axo_edges_list, axo_labels, biggest_bbox)
