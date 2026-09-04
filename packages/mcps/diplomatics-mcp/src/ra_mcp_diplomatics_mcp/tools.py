"""FastMCP server definition for diplomatics search tools."""

from fastmcp import FastMCP

from .mpo_tool import register_mpo_tool
from .sdhk_tool import register_sdhk_tool


diplomatics_mcp = FastMCP(
    name="ra-diplomatics-mcp",
    instructions=(
        "Search medieval Swedish documents: SDHK (44,000+ medieval charters before 1540) "
        "and MPO (23,000+ medieval parchment fragments). "
        "MPO fragments are cited by signatur 'Fr <number>' (e.g. 'Fr 6000'); the number is the MPO ID, "
        "and search_mpo resolves 'Fr 6000', 'MPO 6000' or '6000' to that exact fragment. "
        "Both return IIIF manifest URLs — use view_manifest to view document images."
    ),
)

register_sdhk_tool(diplomatics_mcp)
register_mpo_tool(diplomatics_mcp)
