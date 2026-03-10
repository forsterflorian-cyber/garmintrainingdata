export function setPanelTone(node, tone = "neutral") {
  if (node) {
    node.dataset.tone = tone;
  }
}
