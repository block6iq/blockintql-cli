"""Graph visualization templates"""

class GraphTemplate:
    """Base template for graph visualizations"""
    
    FORCE_DIRECTED = "force"
    TIMELINE = "timeline"
    SANKEY = "sankey"
    TREE = "tree"
    
    @staticmethod
    def get_template(graph_type: str) -> str:
        """Get HTML template for graph type"""
        templates = {
            "force": GraphTemplate._force_directed(),
            "timeline": GraphTemplate._timeline(),
            "sankey": GraphTemplate._sankey(),
            "tree": GraphTemplate._tree(),
        }
        return templates.get(graph_type, templates["force"])
    
    @staticmethod
    def _force_directed() -> str:
        return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>BlockINTQL Graph</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
body { margin: 0; font-family: monospace; background: #0a0a0a; }
svg { width: 100vw; height: 100vh; }
.node { cursor: pointer; }
.node circle { stroke: #fff; stroke-width: 2px; }
.link { stroke: #999; stroke-opacity: 0.6; }
.label { fill: #fff; font-size: 10px; pointer-events: none; }
#controls { position: absolute; top: 20px; right: 20px; background: rgba(0,0,0,0.8); padding: 15px; border-radius: 5px; color: #fff; }
</style>
</head>
<body>
<div id="controls">
  <div>Nodes: <span id="node-count">0</span></div>
  <div>Links: <span id="link-count">0</span></div>
</div>
<svg id="graph"></svg>
<script>
// Data will be injected here
const data = {{DATA}};

const svg = d3.select("#graph");
const width = window.innerWidth;
const height = window.innerHeight;

const simulation = d3.forceSimulation(data.nodes)
    .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
    .force("charge", d3.forceManyBody().strength(-300))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(30));

const link = svg.append("g")
    .selectAll("line")
    .data(data.links)
    .join("line")
    .attr("class", "link")
    .attr("stroke-width", d => Math.sqrt(d.value || 1));

const node = svg.append("g")
    .selectAll("g")
    .data(data.nodes)
    .join("g")
    .attr("class", "node")
    .call(d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended));

node.append("circle")
    .attr("r", d => d.size || 10)
    .attr("fill", d => d.color || "#69b3a2");

node.append("text")
    .attr("class", "label")
    .attr("dx", 12)
    .attr("dy", 4)
    .text(d => d.label || d.id);

document.getElementById("node-count").textContent = data.nodes.length;
document.getElementById("link-count").textContent = data.links.length;

simulation.on("tick", () => {
    link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
    
    node.attr("transform", d => `translate(${d.x},${d.y})`);
});

function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
}

function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
}

function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
}
</script>
</body>
</html>"""
