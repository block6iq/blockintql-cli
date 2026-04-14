"""Graph visualization templates"""

class GraphTemplate:
    """Base template for graph visualizations"""
    
    FORCE_DIRECTED = "force"
    
    @staticmethod
    def get_template(graph_type: str) -> str:
        """Get HTML template for graph type"""
        return GraphTemplate._force_directed()
    
    @staticmethod
    def _force_directed() -> str:
        return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>BlockINTQL Investigation Graph</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
body{margin:0;font-family:monospace;background:#0a0a0a;overflow:hidden}
svg{width:100vw;height:100vh}
.node{cursor:pointer}
.node circle{stroke:#fff;stroke-width:2px}
.link{stroke:#999;stroke-opacity:0.6}
.label{fill:#fff;font-size:10px;pointer-events:none}
#controls{position:absolute;top:20px;right:20px;background:rgba(0,0,0,0.9);padding:15px;border-radius:5px;color:#fff;border:1px solid #333}
.stat{margin:5px 0;font-size:12px}
</style>
</head>
<body>
<div id="controls">
  <div class="stat">🔍 <strong>Investigation Graph</strong></div>
  <div class="stat">Nodes: <span id="node-count">0</span></div>
  <div class="stat">Links: <span id="link-count">0</span></div>
  <div class="stat" style="margin-top:10px;color:#888">Drag to explore</div>
</div>
<svg id="graph"></svg>
<script>
const data = {{DATA}};
const svg = d3.select("#graph");
const width = window.innerWidth;
const height = window.innerHeight;

const simulation = d3.forceSimulation(data.nodes)
    .force("link", d3.forceLink(data.links).id(d => d.id).distance(150))
    .force("charge", d3.forceManyBody().strength(-400))
    .force("center", d3.forceCenter(width/2, height/2))
    .force("collision", d3.forceCollide().radius(40));

const link = svg.append("g")
    .selectAll("line")
    .data(data.links)
    .join("line")
    .attr("class", "link")
    .attr("stroke-width", d => Math.sqrt(d.value || 1) * 2);

const node = svg.append("g")
    .selectAll("g")
    .data(data.nodes)
    .join("g")
    .attr("class", "node")
    .call(d3.drag()
        .on("start", (e) => { if(!e.active) simulation.alphaTarget(0.3).restart(); e.subject.fx=e.subject.x; e.subject.fy=e.subject.y; })
        .on("drag", (e) => { e.subject.fx=e.x; e.subject.fy=e.y; })
        .on("end", (e) => { if(!e.active) simulation.alphaTarget(0); e.subject.fx=null; e.subject.fy=null; }));

node.append("circle")
    .attr("r", d => d.size || 10)
    .attr("fill", d => d.color || "#69b3a2");

node.append("text")
    .attr("class", "label")
    .attr("dx", 15)
    .attr("dy", 4)
    .text(d => d.label || d.id);

document.getElementById("node-count").textContent = data.nodes.length;
document.getElementById("link-count").textContent = data.links.length;

simulation.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
});
</script>
</body>
</html>"""
