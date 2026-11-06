package dev.aurora;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.option.KeyBinding;
import net.minecraft.client.util.InputUtil;
import net.minecraft.entity.LivingEntity;
import net.minecraft.entity.effect.StatusEffectInstance;
import net.minecraft.entity.effect.StatusEffects;
import net.minecraft.util.Hand;
import net.minecraft.util.hit.BlockHitResult;
import net.minecraft.util.hit.EntityHitResult;
import net.minecraft.util.math.MathHelper;
import net.minecraft.util.math.Vec3d;
import org.lwjgl.glfw.GLFW;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.nio.file.*;
import java.util.*;

public final class AuroraClient implements ClientModInitializer {
 private static final Logger LOG = LoggerFactory.getLogger("aurora");
 private static final Path CONFIG = FabricLoader.getInstance().getConfigDir().resolve("aurora.json");
 private static final Gson GSON = new Gson();
 private boolean forcedSneak, nightVision;
 private KeyBinding menu;
 public static boolean on(Module m) { return m.enabled; }
 public static void save() {
  Map<String,Boolean> values = new LinkedHashMap<>();
  for (Module m : Module.values()) values.put(m.name(), m.enabled);
  try {
   Files.createDirectories(CONFIG.getParent());
   Path tmp = CONFIG.resolveSibling("aurora.json.tmp");
   Files.writeString(tmp, GSON.toJson(values));
   Files.move(tmp, CONFIG, StandardCopyOption.REPLACE_EXISTING);
  } catch (Exception e) { LOG.error("Could not save Aurora settings", e); }
 }
 @Override public void onInitializeClient() {
  if (Files.exists(CONFIG)) try {
   Map<String,Boolean> values = GSON.fromJson(Files.readString(CONFIG), new TypeToken<Map<String,Boolean>>(){}.getType());
   if (values != null) for (Module m : Module.values()) m.enabled = Boolean.TRUE.equals(values.get(m.name()));
  } catch (Exception e) { LOG.warn("Could not read Aurora settings; using defaults", e); }
  menu = KeyBindingHelper.registerKeyBinding(new KeyBinding("Open Aurora", InputUtil.Type.KEYSYM, GLFW.GLFW_KEY_RIGHT_SHIFT, "Aurora"));
  ClientTickEvents.END_CLIENT_TICK.register(this::tick);
  HudRenderCallback.EVENT.register((draw, counter) -> {
   MinecraftClient c = MinecraftClient.getInstance();
   if (!on(Module.HUD) || c.player == null || c.options.hudHidden) return;
   List<String> lines = new ArrayList<>();
   lines.add("AURORA / PRIVATE EDITION");
   lines.add(String.format(Locale.ROOT,"XYZ %.1f / %.1f / %.1f", c.player.getX(),c.player.getY(),c.player.getZ()));
   Vec3d v = c.player.getVelocity();
   lines.add(String.format(Locale.ROOT,"%.1f blocks/s | %d FPS",Math.sqrt(v.x*v.x+v.z*v.z)*20,c.getCurrentFps()));
   for (Module m : Module.values()) if (m.enabled && m != Module.HUD) lines.add(m.label);
   int y=10;
   for (String line : lines) { draw.fill(8,y-2,18+c.textRenderer.getWidth(line),y+11,0x99202b3e); draw.drawTextWithShadow(c.textRenderer,line,13,y,0xffb8e9ff); y+=15; }
  });
 }
 private void tick(MinecraftClient c) {
  while (menu.wasPressed()) c.setScreen(c.currentScreen instanceof AuroraScreen ? null : new AuroraScreen());
  if (c.player == null || c.world == null) { forcedSneak=false; nightVision=false; return; }
  var p = c.player;
  if (forcedSneak) { c.options.sneakKey.setPressed(InputUtil.isKeyPressed(c.getWindow().getHandle(), GLFW.GLFW_KEY_LEFT_SHIFT)); forcedSneak=false; }
  if (on(Module.FULLBRIGHT)) {
   if (!p.hasStatusEffect(StatusEffects.NIGHT_VISION) || (nightVision && p.getStatusEffect(StatusEffects.NIGHT_VISION).getDuration()<220)) {
    p.addStatusEffect(new StatusEffectInstance(StatusEffects.NIGHT_VISION,260,0,false,false)); nightVision=true;
   }
  } else if (nightVision) { p.removeStatusEffect(StatusEffects.NIGHT_VISION); nightVision=false; }
  if (c.currentScreen != null || p.isSpectator() || !p.isAlive()) return;
  float forward = p.input.movementForward, sideways=p.input.movementSideways;
  if (on(Module.SPRINT) && forward>0 && !p.isSneaking() && p.getHungerManager().getFoodLevel()>6) p.setSprinting(true);
  if (on(Module.AUTO_JUMP) && p.isOnGround() && p.horizontalCollision && forward>0) p.jump();
  if (on(Module.SAFE_WALK) && p.isOnGround() && !c.options.jumpKey.isPressed()) {
   Vec3d projected=p.getPos().add(p.getVelocity().x*3,0,p.getVelocity().z*3);
   if (c.world.isSpaceEmpty(p,p.getBoundingBox().offset(projected.subtract(p.getPos())).offset(0,-0.55,0))) {
    c.options.sneakKey.setPressed(true); forcedSneak=true;
   }
  }
  if (on(Module.FLIGHT) && !p.hasVehicle()) {
   Vec3d direction = movement(forward,sideways,p.getYaw(),0.5);
   double up=c.options.jumpKey.isPressed()?0.4:c.options.sneakKey.isPressed()?-0.4:0;
   p.setVelocity(direction.x,up,direction.z); p.fallDistance=0;
  } else if (on(Module.SPEED) && p.isOnGround() && !p.isSneaking() && !p.hasVehicle()) {
   Vec3d v=p.getVelocity(); p.setVelocity(v.x*1.35,v.y,v.z*1.35);
  }
  if (on(Module.AUTO_TOOL) && c.options.attackKey.isPressed() && c.crosshairTarget instanceof BlockHitResult hit) {
   var state=c.world.getBlockState(hit.getBlockPos());
   int best=p.getInventory().selectedSlot; float speed=p.getInventory().getStack(best).getMiningSpeedMultiplier(state);
   for (int i=0;i<9;i++) { float candidate=p.getInventory().getStack(i).getMiningSpeedMultiplier(state); if(candidate>speed) { speed=candidate; best=i; } }
   p.getInventory().selectedSlot=best;
  }
  if (on(Module.AIM_ASSIST) && c.options.attackKey.isPressed()) {
   LivingEntity target=nearest(c,4);
   if (target!=null) {
    Vec3d delta=target.getEyePos().subtract(p.getEyePos());
    float yaw=(float)Math.toDegrees(Math.atan2(delta.z,delta.x))-90;
    float pitch=(float)-Math.toDegrees(Math.atan2(delta.y,Math.sqrt(delta.x*delta.x+delta.z*delta.z)));
    p.setYaw(p.getYaw()+MathHelper.clamp(MathHelper.wrapDegrees(yaw-p.getYaw()),-4,4));
    p.setPitch(MathHelper.clamp(p.getPitch()+MathHelper.clamp(pitch-p.getPitch(),-3,3),-90,90));
   }
  }
  if (c.interactionManager == null || p.getAttackCooldownProgress(0)<0.95f || p.isUsingItem()) return;
  LivingEntity target=null;
  if (on(Module.TRIGGER) && c.crosshairTarget instanceof EntityHitResult hit && hit.getEntity() instanceof LivingEntity living && valid(c,living,3)) target=living;
  if (target==null && on(Module.AURA)) target=nearest(c,3);
  if (target!=null) { c.interactionManager.attackEntity(p,target); p.swingHand(Hand.MAIN_HAND); }
 }
 private static boolean valid(MinecraftClient c, LivingEntity e, double range) {
  return e!=c.player && e.isAlive() && !e.isSpectator() && !e.isTeammate(c.player) && c.player.squaredDistanceTo(e)<=range*range && c.player.canSee(e);
 }
 private static LivingEntity nearest(MinecraftClient c,double range) {
  return c.world.getEntitiesByClass(LivingEntity.class,c.player.getBoundingBox().expand(range),e->valid(c,e,range)).stream().min(Comparator.comparingDouble(c.player::squaredDistanceTo)).orElse(null);
 }
 static Vec3d movement(float forward,float side,float yaw,double speed) {
  double length=Math.hypot(forward,side); if (length<0.001) return Vec3d.ZERO;
  double rad=Math.toRadians(yaw);
  return new Vec3d((-Math.sin(rad)*forward+Math.cos(rad)*side)/length*speed,0,(Math.cos(rad)*forward+Math.sin(rad)*side)/length*speed);
 }
}
