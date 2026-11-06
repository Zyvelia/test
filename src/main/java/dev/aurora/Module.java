package dev.aurora;

public enum Module {
 SPRINT("Sprint", "Movement", "Sprints while moving forward, when hunger and terrain allow."),
 SPEED("Speed", "Movement", "Multiplies horizontal movement by 1.35 while walking on ground."),
 FLIGHT("Flight", "Movement", "Moves freely through the air. Jump rises; sneak descends. Server rules may override it."),
 AUTO_JUMP("Auto jump", "Movement", "Jumps when you walk into a block while grounded."),
 SAFE_WALK("Safe walk", "Movement", "Holds sneak near ledges to reduce accidental falls."),
 AIM_ASSIST("Aim assist", "Combat", "While holding attack, gently aims at a visible living target within four blocks."),
 TRIGGER("Trigger attack", "Combat", "Attacks the living entity under your crosshair when the attack cooldown is ready."),
 AURA("Auto attack", "Combat", "Attacks the closest visible living target within three blocks, respecting cooldown."),
 AUTO_TOOL("Auto tool", "Player", "While mining, selects the hotbar tool with the best mining speed for that block."),
 FULLBRIGHT("Fullbright", "Visual", "Applies local night vision; preserves existing night vision when possible."),
 HUD("Status HUD", "Visual", "Shows coordinates, speed, FPS, and enabled modules in the upper left.");
 public final String label, category, description;
 public boolean enabled;
 Module(String label, String category, String description) {
  this.label=label; this.category=category; this.description=description;
 }
}
