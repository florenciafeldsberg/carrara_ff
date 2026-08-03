# libraries
import sys

_repo_dir = r"C:\Users\slantis-temp\Desktop\git\carrara_ff"
if _repo_dir not in sys.path:
    sys.path.append(_repo_dir)

for _mod_name in ("Carrara_Geometry_Handling", "Carrara_Layout_Formatting"):
    if _mod_name in sys.modules:
        del sys.modules[_mod_name]

import Carrara_Geometry_Handling as geometry_handling
import Carrara_Layout_Formatting as layout_formatting

angle = 25
piece_prefix = "A"
gutter = 5.0
json_path = "C:/Users/slantis-temp/Desktop/git/carrara_ff/carrara_pieces.json"

# main
def main():
    (moved_objs, bbox_brep, split_pieces, recentered_pieces, capped_pieces, oriented_pieces,
     planar_pieces, labels, axo_edges_list, axo_labels, biggest_bbox) = geometry_handling.main(layer_name, angle, piece_prefix)

    laid_out, laid_labels, json_written = layout_formatting.main(
        planar_pieces, labels, axo_edges_list, axo_labels, gutter, json_path
    )

    return moved_objs, bbox_brep, oriented_pieces, planar_pieces, labels, laid_out, laid_labels, json_written

# execution
moved_objs, bbox_brep, oriented_pieces, planar_pieces, labels, laid_out, laid_labels, json_written = main()
