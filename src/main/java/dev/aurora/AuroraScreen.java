package dev.aurora;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.text.Text;
import java.util.Locale;

public final class AuroraScreen extends Screen {
 private String category="Movement", query="";
 private TextFieldWidget search;
 private int left,top,panelWidth,panelHeight;
 public AuroraScreen() { super(Text.literal("Aurora")); }
 @Override protected void init() { rebuild(); }
 private void rebuild() {
  clearChildren(); rows.clear();
  panelWidth=Math.min(540,width-16); panelHeight=Math.min(340,height-16);
  left=(width-panelWidth)/2; top=(height-panelHeight)/2;
  search=new TextFieldWidget(textRenderer,left+14,top+43,panelWidth-28,20,Text.literal("Search modules"));
  search.setPlaceholder(Text.literal("Search modules…")); search.setText(query);
  search.setChangedListener(s->{ query=s; rebuildRows(); });
  addDrawableChild(search);
  int x=left+14;
  for(String cat : new String[]{"Movement","Combat","Player","Visual"}) {
   final String name=cat;
   addDrawableChild(ButtonWidget.builder(Text.literal((category.equals(cat)?"• ":"")+cat),b->{ category=name; rebuild(); }).dimensions(x,top+72,(panelWidth-34)/4,20).build());
   x+=(panelWidth-30)/4;
  }
  addDrawableChild(ButtonWidget.builder(Text.literal("Disable all"),b->{ for(Module m:Module.values()) m.enabled=false; AuroraClient.save(); rebuild(); }).dimensions(left+14,top+panelHeight-29,100,20).build());
  addDrawableChild(ButtonWidget.builder(Text.literal("Done"),b->close()).dimensions(left+panelWidth-84,top+panelHeight-29,70,20).build());
  addRows();
 }
 private final java.util.List<ButtonWidget> rows=new java.util.ArrayList<>();
 private void rebuildRows() { for(ButtonWidget row:rows) remove(row); rows.clear(); addRows(); }
 private void addRows() {
  rows.clear(); int y=top+104; int rowHeight=Math.min(23, Math.max(12,(panelHeight-145)/5));
  for(Module m:Module.values()) {
   if (!m.category.equals(category) || !m.label.toLowerCase(Locale.ROOT).contains(query.toLowerCase(Locale.ROOT))) continue;
   ButtonWidget row=ButtonWidget.builder(label(m), b->{ m.enabled=!m.enabled; b.setMessage(label(m)); AuroraClient.save(); })
    .dimensions(left+14,y,panelWidth-28,rowHeight).tooltip(Tooltip.of(Text.literal(m.description))).build();
   rows.add(row); addDrawableChild(row); y+=rowHeight+2;
  }
 }
 private Text label(Module m) { return Text.literal((m.enabled?"§b● ON   §f":"§7○ OFF  §f")+m.label); }
 @Override public void render(DrawContext d,int mouseX,int mouseY,float delta) {
  d.fill(0,0,width,height,0x48202b40);
  d.fill(left,top,left+panelWidth,top+panelHeight,0xb312192b);
  d.fill(left,top,left+panelWidth,top+2,0xff8cdcff);
  d.drawTextWithShadow(textRenderer,"A U R O R A",left+14,top+12,0xffa8e5ff);
  d.drawTextWithShadow(textRenderer,"PRIVATE EDITION  /  Hover a toggle for details",left+14,top+28,0xffa3aec6);
  super.render(d,mouseX,mouseY,delta);
 }
 @Override public boolean shouldPause() { return false; }
 @Override public void close() { AuroraClient.save(); super.close(); }
}
