from mcp.server.fastmcp import FastMCP
import tools

mcp = FastMCP("blastradius")


@mcp.tool()
def find_function(text: str) -> dict:
    """Search for non-test functions whose full name contains the given text. Use this first when the user gives a partial function name."""
    return tools.find_function(text)


@mcp.tool()
def impact(name: str, max_hops: int = 5) -> dict:
    """List every function that depends on the target function (directly or through up to max_hops calls), with distance in hops. Use for 'what breaks if I change X'. Needs the exact full function name."""
    return tools.impact(name, max_hops)


@mcp.tool()
def tests_for(name: str, max_hops: int = 5) -> dict:
    """List the tests that reach the target function through calls. Use for 'which tests should I run'. Needs the exact full function name."""
    return tools.tests_for(name, max_hops)


@mcp.tool()
def experts(name: str) -> dict:
    """List the people who edited the file containing the target function most, by commit count. Use for 'who should review this'."""
    return tools.experts(name)


@mcp.tool()
def explain_path(source: str, target: str) -> dict:
    """Find the shortest call path from source function to target function. Use to show HOW two pieces of code are connected."""
    return tools.explain_path(source, target)


if __name__ == "__main__":
    mcp.run()
