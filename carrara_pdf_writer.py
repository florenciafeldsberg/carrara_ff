import json
import math
import sys

PT_PER_MM = 72.0 / 25.4


def polygon_edges(points):
    if len(points) > 1 and math.hypot(points[0][0] - points[-1][0], points[0][1] - points[-1][1]) < 1e-9:
        return list(zip(points, points[1:]))
    return list(zip(points, points[1:] + points[:1]))


def polygon_centroid(points):
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    return cx, cy


def build_face_lines(points, avail_w, avail_h, margin_pt, dim_offset_mm, dim_overshoot_mm):
    lines = []
    if not points:
        return lines

    dim_offset = dim_offset_mm
    dim_overshoot = dim_overshoot_mm
    padding = dim_offset + dim_overshoot

    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    min_x, max_x = min(xs) - padding, max(xs) + padding
    min_y, max_y = min(ys) - padding, max(ys) + padding
    width = max_x - min_x
    height = max_y - min_y

    fit_scale = min(avail_w / width, avail_h / height) if width > 0 and height > 0 else 1.0
    offset_x = margin_pt + (avail_w - width * fit_scale) / 2.0 - min_x * fit_scale
    offset_y = margin_pt + (avail_h - height * fit_scale) / 2.0 - min_y * fit_scale

    def to_page(x, y):
        return x * fit_scale + offset_x, y * fit_scale + offset_y

    x0, y0 = points[0]
    px0, py0 = to_page(x0, y0)
    lines.append("0 0 0 RG")
    lines.append("1 w")
    lines.append("{:.2f} {:.2f} m".format(px0, py0))
    for x, y in points[1:]:
        px, py = to_page(x, y)
        lines.append("{:.2f} {:.2f} l".format(px, py))
    lines.append("h S")

    cx, cy = polygon_centroid(points)
    for (x1, y1), (x2, y2) in polygon_edges(points):
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue

        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux

        mid_x, mid_y = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        to_centroid_x, to_centroid_y = cx - mid_x, cy - mid_y
        if nx * to_centroid_x + ny * to_centroid_y > 0:
            nx, ny = -nx, -ny

        d1x, d1y = x1 + nx * dim_offset, y1 + ny * dim_offset
        d2x, d2y = x2 + nx * dim_offset, y2 + ny * dim_offset
        e1x, e1y = x1 + nx * (dim_offset + dim_overshoot), y1 + ny * (dim_offset + dim_overshoot)
        e2x, e2y = x2 + nx * (dim_offset + dim_overshoot), y2 + ny * (dim_offset + dim_overshoot)

        p_x1, p_y1 = to_page(x1, y1)
        p_e1x, p_e1y = to_page(e1x, e1y)
        p_x2, p_y2 = to_page(x2, y2)
        p_e2x, p_e2y = to_page(e2x, e2y)
        p_d1x, p_d1y = to_page(d1x, d1y)
        p_d2x, p_d2y = to_page(d2x, d2y)

        lines.append("0 0 0 RG")
        lines.append("0.3 w")
        lines.append("{:.2f} {:.2f} m {:.2f} {:.2f} l S".format(p_x1, p_y1, p_e1x, p_e1y))
        lines.append("{:.2f} {:.2f} m {:.2f} {:.2f} l S".format(p_x2, p_y2, p_e2x, p_e2y))
        lines.append("{:.2f} {:.2f} m {:.2f} {:.2f} l S".format(p_d1x, p_d1y, p_d2x, p_d2y))

        mid_dim_x, mid_dim_y = to_page((d1x + d2x) / 2.0, (d1y + d2y) / 2.0)
        lines.append("BT /F1 6 Tf {:.2f} {:.2f} Td ({:.1f}) Tj ET".format(mid_dim_x, mid_dim_y, length))

    return lines


def build_axo_lines(edges, avail_w, avail_h, margin_pt):
    lines = []
    all_points = [pt for edge in edges for pt in edge]
    if not all_points:
        return lines

    xs = [pt[0] for pt in all_points]
    ys = [pt[1] for pt in all_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y

    fit_scale = min(avail_w / width, avail_h / height) if width > 0 and height > 0 else 1.0
    offset_x = margin_pt + (avail_w - width * fit_scale) / 2.0 - min_x * fit_scale
    offset_y = margin_pt + (avail_h - height * fit_scale) / 2.0 - min_y * fit_scale

    lines.append("0 0 0 RG")
    lines.append("0.5 w")
    for edge in edges:
        if not edge:
            continue
        x0, y0 = edge[0]
        lines.append("{:.2f} {:.2f} m".format(x0 * fit_scale + offset_x, y0 * fit_scale + offset_y))
        for x, y in edge[1:]:
            lines.append("{:.2f} {:.2f} l".format(x * fit_scale + offset_x, y * fit_scale + offset_y))
        lines.append("S")

    return lines


def make_pdf(json_path, pdf_path, page_width_mm=210.0, page_height_mm=297.0, margin_mm=10.0, frame_offset_mm=5.0,
             dim_offset_mm=4.0, dim_overshoot_mm=1.5):
    with open(json_path, "r") as f:
        pieces = json.load(f)

    objects = []

    def add_object(content_bytes):
        objects.append(content_bytes)
        return len(objects)

    font_obj_num = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_w_pt = page_width_mm * PT_PER_MM
    page_h_pt = page_height_mm * PT_PER_MM
    margin_pt = margin_mm * PT_PER_MM
    frame_offset_pt = frame_offset_mm * PT_PER_MM
    avail_w = page_w_pt - 2 * margin_pt
    avail_h = page_h_pt - 2 * margin_pt

    content_obj_nums = []

    for piece in pieces:
        label = piece["label"]
        piece_type = piece.get("type", "face")

        lines = []

        frame_w = page_w_pt - 2 * frame_offset_pt
        frame_h = page_h_pt - 2 * frame_offset_pt
        lines.append("0 0 0 RG")
        lines.append("1 w")
        lines.append("{:.2f} {:.2f} {:.2f} {:.2f} re S".format(frame_offset_pt, frame_offset_pt, frame_w, frame_h))

        if piece_type == "axo":
            lines.extend(build_axo_lines(piece["edges"], avail_w, avail_h, margin_pt))
            print("make_pdf: {} -> pagina axo armada, {} aristas".format(label, len(piece["edges"])))
        else:
            points = piece["points"]
            lines.extend(build_face_lines(points, avail_w, avail_h, margin_pt, dim_offset_mm, dim_overshoot_mm))
            print("make_pdf: {} -> pagina armada, {} puntos".format(label, len(points)))

        lines.append("BT /F1 10 Tf {:.2f} {:.2f} Td ({}) Tj ET".format(
            margin_pt, page_h_pt - margin_pt + 4, label
        ))

        content_str = "\n".join(lines)
        content_bytes = content_str.encode("latin-1", errors="replace")
        stream_obj = (
            b"<< /Length " + str(len(content_bytes)).encode("latin-1") + b" >>\nstream\n"
            + content_bytes + b"\nendstream"
        )
        content_obj_nums.append(add_object(stream_obj))

    pages_obj_num = add_object(b"")

    page_obj_nums = []
    for content_num in content_obj_nums:
        page_bytes = (
            "<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] "
            "/Resources << /Font << /F1 {font} 0 R >> >> /Contents {content} 0 R >>"
        ).format(pages=pages_obj_num, w=page_w_pt, h=page_h_pt, font=font_obj_num, content=content_num)
        page_obj_nums.append(add_object(page_bytes.encode("latin-1")))

    kids = " ".join("{} 0 R".format(n) for n in page_obj_nums)
    objects[pages_obj_num - 1] = "<< /Type /Pages /Kids [{}] /Count {} >>".format(
        kids, len(page_obj_nums)
    ).encode("latin-1")

    catalog_num = add_object("<< /Type /Catalog /Pages {} 0 R >>".format(pages_obj_num).encode("latin-1"))

    out = bytearray()
    out += b"%PDF-1.4\n"
    offsets = [0] * (len(objects) + 1)

    for i, obj_bytes in enumerate(objects, start=1):
        offsets[i] = len(out)
        out += "{} 0 obj\n".format(i).encode("latin-1")
        out += obj_bytes
        out += b"\nendobj\n"

    xref_offset = len(out)
    out += "xref\n0 {}\n".format(len(objects) + 1).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for i in range(1, len(objects) + 1):
        out += "{:010d} 00000 n \n".format(offsets[i]).encode("latin-1")

    out += b"trailer\n"
    out += "<< /Size {} /Root {} 0 R >>\n".format(len(objects) + 1, catalog_num).encode("latin-1")
    out += b"startxref\n"
    out += str(xref_offset).encode("latin-1")
    out += b"\n%%EOF"

    with open(pdf_path, "wb") as f:
        f.write(out)

    print("make_pdf: PDF escrito en {}, total paginas={}".format(pdf_path, len(page_obj_nums)))
    return pdf_path


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "carrara_pieces.json"
    pdf_path = sys.argv[2] if len(sys.argv) > 2 else "carrara_output.pdf"
    make_pdf(json_path, pdf_path)
