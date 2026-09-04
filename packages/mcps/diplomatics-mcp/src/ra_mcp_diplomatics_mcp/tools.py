"""FastMCP server definition for diplomatics search tools."""

from fastmcp import FastMCP

from .mpo_tool import register_mpo_tool
from .sdhk_tool import register_sdhk_tool


diplomatics_mcp = FastMCP(
    name="ra-diplomatics-mcp",
    instructions=(
        "Search medieval Swedish documents: SDHK (44,000+ medieval charters before 1540) "
        "and MPO (23,000+ medieval parchment fragments). "
        "MPO fragments are numbered, and Riksarkivet writes that number as a signature: fragment 6000 is 'Fr 6000'. "
        "When a user names a fragment ('Fr 6000', 'MPO 6000', a bare '6000', or a bildvisning/IIIF URL), "
        "pass it to search_mpo as mpo_id for an exact lookup instead of a keyword search. "
        "Both tools return IIIF manifest URLs — use view_manifest to view document images."
    ),
)

register_sdhk_tool(diplomatics_mcp)
register_mpo_tool(diplomatics_mcp)
