# libraries
import json

import Rhino.Geometry as rg

# tools
def group_by_piece(pieces, labels):
    groups = {}
    order = []
    for p, label in zip(pieces, labels):
        piece_label = label.split("_")[0]
        if piece_label not in groups:
            groups[piece_label] = []
            order.append(piece_label)
        groups[piece_label].append((label, p))

    print("group_by_piece: piezas agrupadas={}".format(len(order)))
    return groups, order

def layout_grid(pieces, labels, gutter):
    groups, order = group_by_piece(pieces, labels)

    laid_out = []
    laid_labels = []
    y_cursor = 0.0

    for piece_label in order:
        items = groups[piece_label]
        x_cursor = 0.0
        row_height = 0.0

        for label, p in items:
            bbox = p.GetBoundingBox(True)
            size = bbox.Max - bbox.Min

            xf = rg.Transform.Translation(x_cursor - bbox.Min.X, y_cursor - bbox.Min.Y, -bbox.Min.Z)
            p2 = p.Duplicate()
            p2.Transform(xf)

            print("layout_grid: {} -> x={}, y={}".format(label, x_cursor, y_cursor))

            laid_out.append(p2)
            laid_labels.append(label)

            x_cursor += size.X + gutter
            row_height = max(row_height, size.Y)

        y_cursor += row_height + gutter

    print("layout_grid: total piezas ubicadas={}".format(len(laid_out)))
    return laid_out, laid_labels

def piece_outline_points(piece):
    face = piece.Faces[0]
    loop_curve = face.OuterLoop.To3dCurve()

    success, polyline = loop_curve.TryGetPolyline()
    if success:
        pts = list(polyline)
    else:
        params = loop_curve.DivideByCount(64, True)
        pts = [loop_curve.PointAt(t) for t in params] if params else []

    return [[pt.X, pt.Y] for pt in pts]

def export_to_json(pieces, labels, axo_edges_list, axo_labels, path):
    data = []
    for p, label in zip(pieces, labels):
        points = piece_outline_points(p)
        bbox = p.GetBoundingBox(True)
        size = bbox.Max - bbox.Min

        print("export_to_json: {} -> {} puntos, width={}, height={}".format(label, len(points), size.X, size.Y))

        data.append({
            "type": "face",
            "label": label,
            "points": points,
            "width": size.X,
            "height": size.Y,
        })

    for edges_2d, axo_label in zip(axo_edges_list, axo_labels):
        print("export_to_json: {} -> {} aristas".format(axo_label, len(edges_2d)))
        data.append({
            "type": "axo",
            "label": axo_label,
            "edges": edges_2d,
        })

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print("export_to_json: escrito en {}, total entradas={}".format(path, len(data)))
    return path

# main
def main(planar_pieces, labels, axo_edges_list, axo_labels, gutter, json_path):
    laid_out, laid_labels = layout_grid(planar_pieces, labels, gutter)
    json_written = export_to_json(planar_pieces, labels, axo_edges_list, axo_labels, json_path)

    return laid_out, laid_labels, json_written
