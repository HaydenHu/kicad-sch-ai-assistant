"""
KiCad Sch AI Pin Assistant - GUI
Layout: top bar | split left(chat+input+thumb) / right(pin table)
"""

import base64, io, json, os, sys
from datetime import datetime

import wx
import wx.grid as gridlib
from i18n import T

DBG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")

def _log(msg):
    try:
        with open(DBG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

class PinData:
    def __init__(self, number="", name="", etype="passive", shape="line", side="left", index=0):
        self.number = number; self.name = name; self.etype = etype
        self.shape = shape; self.side = side; self.index = index

ETYPE_CHOICES = ["passive","input","output","bidirectional","tri_state",
    "power_in","power_out","open_collector","open_emitter","no_connect","unspecified"]
SHAPE_CHOICES = ["line","inverted","clock","inverted_clock",
    "input_low","clock_low","output_low","non_logic"]
SIDE_CHOICES = ["left","right","top","bottom"]

class ThumbnailButton(wx.BitmapButton):
    def __init__(self, parent, size=(100,80)):
        empty = wx.Bitmap(size[0], size[1])
        super().__init__(parent, bitmap=empty, size=size)
        self._png = b""
        self.SetMinSize(size)
        self.SetToolTip("Click to enlarge")
        self.Bind(wx.EVT_BUTTON, self._on_click)

    def set_image(self, png_bytes):
        self._png = png_bytes
        if png_bytes and len(png_bytes) > 10:
            try:
                img = wx.Image(io.BytesIO(png_bytes))
                if img.IsOk():
                    w, h = self.GetSize()
                    iw, ih = img.GetWidth(), img.GetHeight()
                    scale = min(w/iw, h/ih, 1.0)
                    bmp = wx.Bitmap(img.Scale(int(iw*scale), int(ih*scale)))
                    self.SetBitmap(bmp)
                    self.SetToolTip("Click to enlarge")
                    return
            except Exception: pass
        empty = wx.Bitmap(self.GetSize()[0], self.GetSize()[1])
        self.SetBitmap(empty)
        self.SetToolTip("No image")

    def get_png(self): return self._png

    def clear(self):
        self._png = b""
        empty = wx.Bitmap(self.GetSize()[0], self.GetSize()[1])
        self.SetBitmap(empty)
        self.SetToolTip("")

    def _on_click(self, event):
        if self._png and len(self._png) > 10:
            img = wx.Image(io.BytesIO(self._png))
            if not img.IsOk(): return
            iw, ih = img.GetWidth(), img.GetHeight()
            max_w, max_h = 700, 500
            sc = min(max_w/iw, max_h/ih, 1.0)
            nw, nh = int(iw*sc), int(ih*sc)
            bmp = wx.Bitmap(img.Scale(nw, nh, wx.IMAGE_QUALITY_HIGH))
            dlg = wx.Dialog(self, title="Image Preview", style=wx.DEFAULT_DIALOG_STYLE)
            dlg.SetClientSize((nw+20, nh+20))
            dlg.CentreOnParent()
            p = wx.Panel(dlg)
            s = wx.BoxSizer(wx.VERTICAL)
            sb = wx.StaticBitmap(p, bitmap=bmp)
            s.Add(sb, 1, wx.EXPAND|wx.ALL, 10)
            sb.Bind(wx.EVT_LEFT_DOWN, lambda e: dlg.EndModal(0))
            dlg.Bind(wx.EVT_CHAR_HOOK, lambda e: dlg.EndModal(0) if e.GetKeyCode()==wx.WXK_ESCAPE else e.Skip())
            p.SetSizer(s)
            dlg.ShowModal()
            dlg.Destroy()

class ChatMessagePanel(wx.Panel):
    def __init__(self, parent, role, text, image_bytes=None):
        super().__init__(parent)
        colours = {"user": wx.Colour(227,242,253), "ai": wx.Colour(243,255,243), "system": wx.Colour(255,248,225)}
        self.SetBackgroundColour(colours.get(role, wx.WHITE))
        main = wx.BoxSizer(wx.HORIZONTAL)
        av = {"user":"[You]", "ai":"[AI]", "system":"[*]"}
        avatar = wx.StaticText(self, label=av.get(role,"[ ]"))
        main.Add(avatar, 0, wx.ALIGN_TOP|wx.ALL, 4)
        content = wx.BoxSizer(wx.VERTICAL)
        tl = wx.StaticText(self, label=datetime.now().strftime("%H:%M"))
        tl.SetForegroundColour(wx.Colour(150,150,150))
        content.Add(tl, 0, wx.BOTTOM, 2)
        txt = wx.StaticText(self, label=text)
        txt.Wrap(380); content.Add(txt, 0, wx.EXPAND)
        if image_bytes and len(image_bytes) > 10:
            try:
                img = wx.Image(io.BytesIO(image_bytes))
                if img.IsOk():
                    thumb = wx.Bitmap(img.Scale(80,60))
                    sb = wx.StaticBitmap(self, bitmap=thumb)
                    sb.SetToolTip("Click to enlarge")
                    sb.Bind(wx.EVT_LEFT_DOWN, lambda e: self._preview(image_bytes))
                    content.Add(sb, 0, wx.TOP|wx.LEFT, 4)
            except Exception: pass
        main.Add(content, 1, wx.EXPAND|wx.ALL, 4)
        self.SetSizer(main); self.SetMinSize((350,-1))

    def _preview(self, png_bytes):
        dlg = wx.Dialog(self, title=T("preview_title"), style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        dlg.SetSize((600,480)); p = wx.Panel(dlg); s = wx.BoxSizer(wx.VERTICAL)
        img = wx.Image(io.BytesIO(png_bytes))
        sc = min(580/img.GetWidth(), 440/img.GetHeight(), 1.0)
        bmp = wx.Bitmap(img.Scale(int(img.GetWidth()*sc), int(img.GetHeight()*sc)))
        sb = wx.StaticBitmap(p, bitmap=bmp)
        s.Add(sb, 1, wx.EXPAND|wx.ALL|wx.ALIGN_CENTER, 10)
        sb.Bind(wx.EVT_LEFT_DOWN, lambda e: dlg.EndModal(0))
        dlg.Bind(wx.EVT_KEY_DOWN, lambda e: dlg.EndModal(0) if e.GetKeyCode()==wx.WXK_ESCAPE else e.Skip())
        p.SetSizer(s); dlg.ShowModal(); dlg.Destroy()

class PinTableGrid(gridlib.Grid):
    COLS = ["#", "Pin Name", "Pin Number", "Type", "Shape", "Side"]
    def __init__(self, parent):
        super().__init__(parent, style=wx.WANTS_CHARS)
        self.CreateGrid(0, len(self.COLS))
        for i, l in enumerate(self.COLS): self.SetColLabelValue(i, l)
        self.SetColSize(0,30); self.SetColSize(1,140); self.SetColSize(2,90)
        self.SetColSize(3,110); self.SetColSize(4,110); self.SetColSize(5,55)
        self.SetRowLabelSize(30)
        self.SetColAttr(3, self._attr(gridlib.GridCellChoiceEditor(ETYPE_CHOICES)))
        self.SetColAttr(4, self._attr(gridlib.GridCellChoiceEditor(SHAPE_CHOICES)))
        self.SetColAttr(5, self._attr(gridlib.GridCellChoiceEditor(SIDE_CHOICES)))
    def _attr(self, e): a = gridlib.GridCellAttr(); a.SetEditor(e); return a
    def get_pins(self):
        pins = []
        for r in range(self.GetNumberRows()):
            nm = self.GetCellValue(r,1).strip(); nb = self.GetCellValue(r,2).strip()
            if not nm and not nb: continue
            pins.append(PinData(number=nb, name=nm,
                etype=self.GetCellValue(r,3).strip() or "passive",
                shape=self.GetCellValue(r,4).strip() or "line",
                side=self.GetCellValue(r,5).strip() or "left"))
        return pins
    def set_pins(self, plist):
        if self.GetNumberRows()>0: self.DeleteRows(0, self.GetNumberRows())
        if not plist: return
        self.AppendRows(len(plist))
        for i, p in enumerate(plist):
            self.SetCellValue(i,0,str(i+1)); self.SetCellValue(i,1,p.name)
            self.SetCellValue(i,2,p.number)
            self.SetCellValue(i,3,p.etype if p.etype in ETYPE_CHOICES else "passive")
            self.SetCellValue(i,4,p.shape if p.shape in SHAPE_CHOICES else "line")
            self.SetCellValue(i,5,p.side if p.side in SIDE_CHOICES else "left")
            self.SetReadOnly(i,0,True)
        self.AutoSize()

class SchAiAssistantDialog(wx.Dialog):
    def __init__(self, parent, plugin_dir):
        super().__init__(parent, title=T("title"), size=(1100,750),
                         style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER|wx.MAXIMIZE_BOX|wx.MINIMIZE_BOX)
        self.plugin_dir = plugin_dir
        self.api_key = self._load_api_key()
        self._last_image_bytes = None
        # Chat log uses wx.TextCtrl for native scrolling
        self._init_ui()
        self.CentreOnParent()
        _log("Dialog initialized")

    def _init_ui(self):
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        # Top bar
        top_bar = wx.BoxSizer(wx.HORIZONTAL)
        self.settings_toggle = wx.Button(panel, label=T("settings_btn"), size=(70,28))
        self.settings_toggle.Bind(wx.EVT_BUTTON, self._on_settings)
        top_bar.Add(self.settings_toggle, 0, wx.RIGHT, 6)
        self.copy_btn = wx.Button(panel, label=T("copy_editor"), size=(150,28))
        self.copy_btn.SetBackgroundColour(wx.Colour(39, 174, 96))  # green
        self.copy_btn.Bind(wx.EVT_BUTTON, self._on_copy_editor)
        top_bar.Add(self.copy_btn, 0, wx.RIGHT, 6)
        self.save_btn = wx.Button(panel, label=T("save_sym"), size=(120,28))
        self.save_btn.Bind(wx.EVT_BUTTON, self._on_save_sym)
        top_bar.Add(self.save_btn, 0, wx.RIGHT, 6)
        self.export_btn = wx.Button(panel, label=T("export_json"), size=(100,28))
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_json)
        top_bar.Add(self.export_btn, 0)
        top_bar.AddStretchSpacer(1)
        main_sizer.Add(top_bar, 0, wx.EXPAND|wx.ALL, 4)

        # Splitter
        self.splitter = wx.SplitterWindow(panel, style=wx.SP_3D)
        self.splitter.SetMinimumPaneSize(150)

        # Left: Chat
        self.chat_panel = wx.Panel(self.splitter)
        chat_sizer = wx.BoxSizer(wx.VERTICAL)
        # Chat log (text-based, colored, scrolling works natively)
        self.msg_window = wx.TextCtrl(self.chat_panel, style=wx.TE_MULTILINE|wx.TE_READONLY|wx.TE_RICH|wx.HSCROLL)
        self.msg_window.SetMinSize((300,100))
        self.msg_window.SetBackgroundColour(wx.Colour(250,250,250))
        self._msg_ranges = []  # list of (start, end, role) for recoloring
        start = self.msg_window.GetLastPosition()
        self.msg_window.AppendText("*** Welcome! Paste a datasheet pin diagram, then click Send. ***\n")
        self._msg_ranges.append((start, self.msg_window.GetLastPosition(), "system"))
        chat_sizer.Add(self.msg_window, 1, wx.EXPAND|wx.ALL, 4)

        # Input bar
        input_row = wx.BoxSizer(wx.HORIZONTAL)
        self.thumb = ThumbnailButton(self.chat_panel, (140,90))
        self.thumb.SetMinSize((140,90)); self.thumb.Hide()
        input_row.Add(self.thumb, 0, wx.RIGHT, 8)
        input_inner = wx.BoxSizer(wx.VERTICAL)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        p_btn = wx.Button(self.chat_panel, label=T("paste"), size=(70,24))
        p_btn.Bind(wx.EVT_BUTTON, self._on_paste)
        btn_row.Add(p_btn, 0, wx.RIGHT, 4)
        f_btn = wx.Button(self.chat_panel, label=T("file"), size=(60,24))
        f_btn.Bind(wx.EVT_BUTTON, self._on_load_file)
        btn_row.Add(f_btn, 0, wx.RIGHT, 4)
        r_btn = wx.Button(self.chat_panel, label=T("symbol_recog"), size=(80,24))
        r_btn.SetToolTip("Analyze image and extract pins to table")
        r_btn.SetBackgroundColour(wx.Colour(255, 215, 0))  # gold
        r_btn.Bind(wx.EVT_BUTTON, self._on_analyze)
        btn_row.Add(r_btn, 0)
        input_inner.Add(btn_row, 0, wx.BOTTOM, 2)
        prompt_row = wx.BoxSizer(wx.HORIZONTAL)
        self.prompt_text = wx.TextCtrl(self.chat_panel, value="", style=wx.TE_MULTILINE|wx.TE_PROCESS_ENTER, size=(-1, 60))
        self.prompt_text.Bind(wx.EVT_TEXT_ENTER, self._on_chat)
        prompt_row.Add(self.prompt_text, 1, wx.EXPAND)
        self.send_btn = wx.Button(self.chat_panel, label=T("send"), size=(60,60))
        self.send_btn.Bind(wx.EVT_BUTTON, self._on_chat)
        prompt_row.Add(self.send_btn, 0, wx.EXPAND|wx.LEFT, 4)
        input_inner.Add(prompt_row, 1, wx.EXPAND)
        input_row.Add(input_inner, 1, wx.EXPAND)
        chat_sizer.Add(input_row, 0, wx.EXPAND|wx.ALL, 4)
        self.chat_panel.SetSizer(chat_sizer)

        # Right: Pin table
        right_panel = wx.Panel(self.splitter)
        right_panel.SetMinSize(wx.Size(220,0))
        rs = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(right_panel, label=T("extracted_pins") + ":")
        rs.Add(lbl, 0, wx.BOTTOM, 4)
        self.pin_grid = PinTableGrid(right_panel)
        rs.Add(self.pin_grid, 1, wx.EXPAND)
        right_panel.SetSizer(rs)

        self.splitter.SplitVertically(self.chat_panel, right_panel, -420)
        main_sizer.Add(self.splitter, 1, wx.EXPAND|wx.ALL, 4)
        panel.SetSizer(main_sizer)

        self._create_settings_dlg()

        accel = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord("V"), wx.ID_PASTE)])
        self.SetAcceleratorTable(accel)
        self.Bind(wx.EVT_MENU, lambda e: self._on_paste(None), id=wx.ID_PASTE)

        # Drag-and-drop support
        class DropTarget(wx.FileDropTarget):
            def __init__(self, cb):
                super().__init__(); self.cb = cb
            def OnDropFiles(self, x, y, files):
                if files: self.cb(files[0]); return True
        panel.SetDropTarget(DropTarget(self._load_file))

    def _create_settings_dlg(self):
        self.settings_dlg = wx.Dialog(self, title=T("settings_title"),
            style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.settings_dlg.SetSize((420,550))
        pan = wx.Panel(self.settings_dlg); sz = wx.BoxSizer(wx.VERTICAL)
        # API
        ab = wx.StaticBox(pan, label="API Settings")
        a_sz = wx.StaticBoxSizer(ab, wx.VERTICAL)
        a_sz.Add(wx.StaticText(a_sz.GetStaticBox(), label="API Key:"), 0, wx.TOP|wx.LEFT, 4)
        self.api_key_ctrl = wx.TextCtrl(a_sz.GetStaticBox(), value=self.api_key, style=wx.TE_PASSWORD)
        a_sz.Add(self.api_key_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        a_sz.Add(wx.StaticText(a_sz.GetStaticBox(), label="Model:"), 0, wx.LEFT, 4)
        self.model_choice = wx.Choice(a_sz.GetStaticBox(), choices=["agnes-2.0-flash","agnes-2.0-pro"])
        self.model_choice.SetSelection(0)
        a_sz.Add(self.model_choice, 0, wx.EXPAND|wx.ALL, 4)
        a_sz.Add(wx.StaticText(a_sz.GetStaticBox(), label="Endpoint:"), 0, wx.LEFT, 4)
        self.endpoint_ctrl = wx.TextCtrl(a_sz.GetStaticBox(), value="https://apihub.agnes-ai.com/v1/chat/completions")
        a_sz.Add(self.endpoint_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        save_api = wx.Button(a_sz.GetStaticBox(), label=T("save_key"))
        save_api.Bind(wx.EVT_BUTTON, self._on_save_api)
        a_sz.Add(save_api, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 4)
        sz.Add(a_sz, 0, wx.EXPAND|wx.ALL|wx.BOTTOM, 8)
        # Symbol
        sb = wx.StaticBox(pan, label="Symbol Settings")
        s_sz = wx.StaticBoxSizer(sb, wx.VERTICAL)
        s_sz.Add(wx.StaticText(s_sz.GetStaticBox(), label="Symbol Name:"), 0, wx.LEFT, 4)
        self.sym_name_ctrl = wx.TextCtrl(s_sz.GetStaticBox(), value="NEW_CHIP")
        s_sz.Add(self.sym_name_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        s_sz.Add(wx.StaticText(s_sz.GetStaticBox(), label="Ref Prefix:"), 0, wx.LEFT, 4)
        self.ref_prefix_ctrl = wx.TextCtrl(s_sz.GetStaticBox(), value="U")
        s_sz.Add(self.ref_prefix_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        s_sz.Add(wx.StaticText(s_sz.GetStaticBox(), label="Pin Length (mm):"), 0, wx.LEFT, 4)
        self.pin_len_ctrl = wx.SpinCtrlDouble(s_sz.GetStaticBox(), value="2.54", min=1.0, max=20, inc=0.5)
        self.pin_len_ctrl.SetDigits(2); s_sz.Add(self.pin_len_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        s_sz.Add(wx.StaticText(s_sz.GetStaticBox(), label="Pin Spacing (mm):"), 0, wx.LEFT, 4)
        self.pin_spacing_ctrl = wx.SpinCtrlDouble(s_sz.GetStaticBox(), value="2.54", min=1.0, max=20, inc=0.5)
        self.pin_spacing_ctrl.SetDigits(2); s_sz.Add(self.pin_spacing_ctrl, 0, wx.EXPAND|wx.ALL, 4)
        self.show_numbers_cb = wx.CheckBox(s_sz.GetStaticBox(), label="Show Pin Numbers")
        self.show_numbers_cb.SetValue(True); s_sz.Add(self.show_numbers_cb, 0, wx.LEFT, 2)
        self.show_names_cb = wx.CheckBox(s_sz.GetStaticBox(), label="Show Pin Names")
        self.show_names_cb.SetValue(True); s_sz.Add(self.show_names_cb, 0, wx.LEFT, 2)
        sz.Add(s_sz, 0, wx.EXPAND|wx.ALL|wx.BOTTOM, 8)
        bb = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(pan, wx.ID_OK, "OK"); cancel_btn = wx.Button(pan, wx.ID_CANCEL, "Cancel")
        bb.AddButton(ok_btn); bb.AddButton(cancel_btn); bb.Realize()
        ok_btn.Bind(wx.EVT_BUTTON, lambda e: self.settings_dlg.EndModal(0))
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.settings_dlg.EndModal(0))
        sz.Add(bb, 0, wx.EXPAND|wx.ALL, 8)
        pan.SetSizer(sz)

    def _on_settings(self, event):
        self.settings_dlg.ShowModal()

    def _on_save_api(self, event):
        self.api_key = self.api_key_ctrl.GetValue().strip()
        with open(os.path.join(self.plugin_dir, "settings.json"), "w") as f:
            json.dump({"api_key": self.api_key}, f)

    def _on_paste(self, event):
        _log("[PASTE] start")
        success = False
        if wx.TheClipboard.Open():
            bmp_obj = wx.BitmapDataObject()
            if wx.TheClipboard.GetData(bmp_obj):
                bmp = bmp_obj.GetBitmap()
                if bmp.IsOk():
                    img = bmp.ConvertToImage()
                    stream = io.BytesIO()
                    if img.SaveFile(stream, wx.BITMAP_TYPE_PNG):
                        self._last_image_bytes = stream.getvalue(); success = True
                        _log(f"[PASTE] BitmapDataObject OK, {len(self._last_image_bytes)} bytes")
            if not success:
                try:
                    img_obj = wx.ImageDataObject()
                    if wx.TheClipboard.GetData(img_obj):
                        img = img_obj.GetImage()
                        if img.IsOk():
                            stream = io.BytesIO()
                            if img.SaveFile(stream, wx.BITMAP_TYPE_PNG):
                                self._last_image_bytes = stream.getvalue(); success = True
                                _log(f"[PASTE] ImageDataObject OK, {len(self._last_image_bytes)} bytes")
                except Exception as ex:
                    _log(f"[PASTE] ImageDataObject failed: {ex}")
            wx.TheClipboard.Close()
        if success:
            self.thumb.set_image(self._last_image_bytes)
            self.thumb.Show(); self.chat_panel.Layout()
            self._add_msg("system", T("image_pasted"))
            _log("[PASTE] success, thumbnail shown")
        else:
            _log("[PASTE] failed - no image on clipboard")
            wx.MessageBox(T("no_clipboard"), "Paste", wx.ICON_INFORMATION)

    def _load_file(self, path):
        """Load image from path into thumbnail (used by File button and drag-drop)."""
        _log(f"[FILE] loading: {path}")
        try:
            img = wx.Image(path)
            if img.IsOk():
                stream = io.BytesIO()
                img.SaveFile(stream, wx.BITMAP_TYPE_PNG)
                png_bytes = stream.getvalue()
                _log(f"[FILE] {len(png_bytes)} bytes PNG")
                self._last_image_bytes = png_bytes
                self.thumb.set_image(png_bytes)
                self.thumb.Show(); self.chat_panel.Layout()
                self._add_msg("system", T("image_loaded", name=os.path.basename(path)))
                _log("[FILE] success")
            else:
                wx.MessageBox(T("unsupported_format"), "Error", wx.ICON_ERROR)
        except Exception as e:
            _log(f"[FILE] exception: {e}")
            wx.MessageBox(str(e), "Error", wx.ICON_ERROR)

    def _on_load_file(self, event):
        _log("[FILE] open dialog")
        with wx.FileDialog(self, "Select Image",
                           wildcard="Images (*.png;*.jpg;*.jpeg;*.bmp)|*.png;*.jpg;*.jpeg;*.bmp",
                           style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._load_file(dlg.GetPath())

    def _on_chat(self, event):
        """Send text-only message to AI chat (runs API in background thread)."""
        prompt = self.prompt_text.GetValue().strip()
        self.prompt_text.Clear()
        if not prompt:
            return
        _log(f"[CHAT] prompt='{prompt[:30]}'")
        self._add_msg("user", prompt)
        self._add_msg("system", "Thinking...")
        import threading
        threading.Thread(target=self._do_chat, args=(prompt,), daemon=True).start()

    def _on_analyze(self, event):
        """Analyze loaded image and extract pins to table (runs API in background thread)."""
        image_bytes = None
        thumb_png = self.thumb.get_png()
        if thumb_png and len(thumb_png) > 10:
            image_bytes = thumb_png
        elif self._last_image_bytes and len(self._last_image_bytes) > 10:
            image_bytes = self._last_image_bytes
        self._last_image_bytes = None
        if not image_bytes:
            wx.MessageBox(T("no_image"), "No Image", wx.ICON_WARNING)
            return
        _log(f"[ANALYZE] image_bytes={len(image_bytes)}")
        self._add_msg("system", T("analyzing"))
        import threading
        threading.Thread(target=self._do_analysis, args=(image_bytes,), daemon=True).start()

    def _do_analysis(self, image_bytes):
        """Background thread: API call, GUI updates via wx.CallAfter."""
        _log(f"[ANALYZE] image_bytes={len(image_bytes)}, api_key={'SET' if self.api_key else 'EMPTY'}")
        if not self.api_key:
            wx.CallAfter(lambda: wx.MessageBox("API key not set.", "No API Key", wx.ICON_WARNING))
            wx.CallAfter(self._remove_last_msg); return
        try:
            from sch_ai_assistant import analyze_pin_diagram
            endpoint = self.endpoint_ctrl.GetValue().strip() or "https://apihub.agnes-ai.com/v1/chat/completions"
            model = self.model_choice.GetStringSelection() or "agnes-2.0-flash"
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            pins = analyze_pin_diagram(self.api_key, model, endpoint, b64)
            _log(f"[ANALYZE] got {len(pins) if pins else 0} pins")
            if pins and len(pins) > 0:
                sides = {}; si = ""
                for p in pins: sides[p.side] = sides.get(p.side, 0) + 1
                si = ", ".join(f"{v} {k}" for k, v in sorted(sides.items()))
                wx.CallAfter(lambda: self._on_analysis_result(pins, si))
            else:
                wx.CallAfter(lambda: wx.MessageBox(T("no_pins"), "No Pins", wx.ICON_WARNING))
        except Exception as e:
            import traceback
            _log(f"[ANALYZE] EXCEPTION: {e}\n{traceback.format_exc()}")
            def show_err(): self._remove_last_msg(); wx.MessageBox(f"Analysis failed:\n{e}", "Error", wx.ICON_ERROR)
            wx.CallAfter(show_err)

    def _on_analysis_result(self, pins, si):
        """Called on main thread after successful pin extraction."""
        try: self._remove_last_msg()
        except Exception: pass
        self.pin_grid.set_pins(pins)
        self._add_msg("ai", f"Found {len(pins)} pins: {si}")
        wx.MessageBox(T("success_pins", n=len(pins), s=si), "Done", wx.ICON_INFORMATION)

    def _do_chat(self, prompt):
        """Background thread: API call, GUI updates via wx.CallAfter."""
        _log(f"[CHAT] prompt='{prompt[:30]}'")
        if not self.api_key:
            wx.CallAfter(lambda: (self._remove_last_msg(), self._add_msg("ai", T("no_api_key"))))
            return
        try:
            import requests
            endpoint = self.endpoint_ctrl.GetValue().strip() or "https://apihub.agnes-ai.com/v1/chat/completions"
            model = self.model_choice.GetStringSelection() or "agnes-2.0-flash"
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            _log(f"[CHAT] reply len={len(content)}")
            wx.CallAfter(self._remove_last_msg)
            wx.CallAfter(lambda: self._add_msg("ai", content))
        except Exception as e:
            import traceback
            _log(f"[CHAT] EXCEPTION: {e}\n{traceback.format_exc()}")
            wx.CallAfter(lambda: (self._remove_last_msg(), self._add_msg("ai", f"Error: {e}")))

    def _add_msg(self, role, text, image_bytes=None):
        """Append text and re-color ALL messages."""
        marker = {"user": ">>", "ai": "<<", "system": "--"}.get(role, "--")
        now = datetime.now().strftime("%H:%M")
        line = f"\n{now} {marker} {text}"
        if image_bytes and len(image_bytes) > 10:
            line += f"\n[image, {len(image_bytes)} bytes]"
        line += "\n"
        start = self.msg_window.GetLastPosition()
        self.msg_window.AppendText(line)
        end = self.msg_window.GetLastPosition()
        self._msg_ranges.append((start, end, role))
        # Re-color ALL messages
        self._recolor_all()
        self.msg_window.ShowPosition(end)

    def _recolor_all(self):
        """Apply colors to all stored message ranges."""
        colours = {"user": wx.Colour(0, 80, 180),
                   "ai": wx.Colour(0, 130, 0),
                   "system": wx.Colour(180, 130, 0)}
        try:
            for s, e, role in self._msg_ranges:
                attr = wx.TextAttr(colours.get(role, wx.BLACK))
                self.msg_window.SetStyle(s, e, attr)
        except Exception:
            pass  # plain text is fine

    def _remove_last_msg(self):
        """Remove last message from chat log and ranges."""
        if self._msg_ranges:
            self._msg_ranges.pop()
            text = self.msg_window.GetValue()
            idx = text.rstrip().rstrip('\n').rfind('\n')
            if idx >= 0:
                self.msg_window.SetValue(text[:idx+1])
            else:
                self.msg_window.SetValue("")
            self._recolor_all()
            self.msg_window.ShowPosition(self.msg_window.GetLastPosition())

    def _on_copy_editor(self, event):
        pins = self.pin_grid.get_pins()
        if not pins: wx.MessageBox(T("no_pins_grid"), "Error", wx.ICON_ERROR); return
        try:
            from sch_ai_assistant import generate_symbol_items
            sn = self.sym_name_ctrl.GetValue().strip() or "NEW_CHIP"
            ref = self.ref_prefix_ctrl.GetValue().strip() or "U"
            txt = generate_symbol_items(sn, ref, pins, self.pin_len_ctrl.GetValue(), self.pin_spacing_ctrl.GetValue())
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(txt)); wx.TheClipboard.Close()
            self._add_msg("system", T("copied", n=len(pins)))
        except Exception as e: wx.MessageBox(str(e), "Error", wx.ICON_ERROR)

    def _on_save_sym(self, event):
        pins = self.pin_grid.get_pins()
        if not pins: wx.MessageBox(T("no_pins_grid"), "Error", wx.ICON_ERROR); return
        try:
            from sch_ai_assistant import generate_kicad_symbol
            sn = self.sym_name_ctrl.GetValue().strip() or "NEW_CHIP"
            ref = self.ref_prefix_ctrl.GetValue().strip() or "U"
            txt = generate_kicad_symbol(sn, ref, pins, self.pin_len_ctrl.GetValue(), self.pin_spacing_ctrl.GetValue(), self.show_numbers_cb.GetValue(), self.show_names_cb.GetValue())
            with wx.FileDialog(self, "Save", defaultFile=f"{sn}.kicad_sym",
                               wildcard="KiCad Symbol (*.kicad_sym)|*.kicad_sym",
                               style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    with open(dlg.GetPath(), "w", encoding="utf-8") as f: f.write(txt)
                    self._add_msg("system", T("saved", path=dlg.GetPath()))
        except Exception as e: wx.MessageBox(str(e), "Error", wx.ICON_ERROR)

    def _on_export_json(self, event):
        pins = self.pin_grid.get_pins()
        if not pins: wx.MessageBox(T("no_pins_grid"), "Error", wx.ICON_ERROR); return
        data = [{"number":p.number,"name":p.name,"type":p.etype,"shape":p.shape,"side":p.side} for p in pins]
        with wx.FileDialog(self, "Export", defaultFile="pins.json",
                           wildcard="JSON (*.json)|*.json",
                           style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                with open(dlg.GetPath(), "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
                self._add_msg("system", T("exported", path=dlg.GetPath()))

    def _load_api_key(self):
        try:
            with open(os.path.join(self.plugin_dir, "settings.json"), "r") as f:
                return json.load(f).get("api_key", "")
        except Exception: return ""
