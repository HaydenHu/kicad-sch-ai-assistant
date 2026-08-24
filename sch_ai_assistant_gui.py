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

MODEL_PRESETS = {
    "agnes-2.5-flash": {
        "endpoint": "https://api.agnes-ai.cn/v1/chat/completions",
        "api_key": "sk-H6dvNuYBnFoRapkiRjvX06xvewuIjqXV3rlaxUTfZIsjNHty"
    },
    "agnes-2.5-pro": {
        "endpoint": "https://api.agnes-ai.cn/v1/chat/completions",
        "api_key": ""
    },
    "minimax-m3": {
        "endpoint": "https://api.minimax.chat/v1",
        "api_key": ""
    },
    "kimi-k2.5": {
        "endpoint": "https://api.moonshot.cn/v1",
        "api_key": ""
    },
    "deepseek-v4-flash-vision-exp": {
        "endpoint": "https://api.deepseek.com/chat/completions",
        "api_key": ""
    },
}

class ThumbnailButton(wx.Panel):
    def __init__(self, parent, size=(100,80)):
        super().__init__(parent, size=size)
        self._png = b""
        self._sb = wx.StaticBitmap(self, bitmap=wx.Bitmap(size[0], size[1]))
        self._sb.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.SetMinSize(size)
        self.SetToolTip("Click to enlarge")

    def set_image(self, png_bytes):
        self._png = png_bytes
        parent = self.GetTopLevelParent()
        preview_dlg = getattr(parent, '_preview_dlg', None)
        preview_sb = getattr(parent, '_preview_sb', None)

        if png_bytes and len(png_bytes) > 10:
            try:
                img = wx.Image(io.BytesIO(png_bytes))
                if img.IsOk():
                    # Thumbnail: fit to widget size
                    w, h = max(self.GetSize()[0], 100), max(self.GetSize()[1], 80)
                    iw, ih = img.GetWidth(), img.GetHeight()
                    sc = min(w/iw, h/ih, 1.0)
                    thumb_bmp = wx.Bitmap(img.Scale(int(iw*sc), int(ih*sc)))
                    self._sb.SetBitmap(thumb_bmp)
                    self.SetToolTip("Click to enlarge")
                    self.Layout()

                    # Update open preview dialog if it exists
                    if preview_dlg and (not hasattr(preview_dlg, 'IsDestroyed') or not preview_dlg.IsDestroyed()):
                        if preview_sb and (not hasattr(preview_sb, 'IsDestroyed') or not preview_sb.IsDestroyed()):
                            pw, ph = 600, 450
                            pw2, ph2 = img.GetWidth(), img.GetHeight()
                            psc = min(pw/pw2, ph/ph2, 1.0)
                            pnbmp = wx.Bitmap(img.Scale(int(pw2*psc), int(ph2*psc), wx.IMAGE_QUALITY_HIGH))
                            preview_sb.SetBitmap(pnbmp)
                            preview_dlg.Raise()
                            preview_dlg.Fit()
                            preview_dlg.Layout()
                    return
            except Exception:
                pass

        empty = wx.Bitmap(max(self.GetSize()[0], 100), max(self.GetSize()[1], 80))
        self._sb.SetBitmap(empty)
        self.SetToolTip("No image")
        self.Layout()

    def get_png(self): return self._png

    def clear(self):
        self._png = b""
        parent = self.GetTopLevelParent()
        preview_dlg = getattr(parent, '_preview_dlg', None)
        preview_sb = getattr(parent, '_preview_sb', None)
        empty = wx.Bitmap(max(self.GetSize()[0], 100), max(self.GetSize()[1], 80))
        self._sb.SetBitmap(empty)
        self.SetToolTip("")
        self.Layout()
        dlg_ok = preview_dlg is not None and (not hasattr(preview_dlg, 'IsDestroyed') or not preview_dlg.IsDestroyed())
        if dlg_ok and preview_sb:
            preview_sb.SetBitmap(empty)
            preview_dlg.Raise()
            preview_dlg.Fit()
            preview_dlg.Layout()

    def _on_click(self, event):
        if not self._png or len(self._png) < 10: return
        try:
            img = wx.Image(io.BytesIO(self._png))
            if not img.IsOk(): return
            iw, ih = img.GetWidth(), img.GetHeight()
            max_w, max_h = 600, 450
            sc = min(max_w/iw, max_h/ih, 1.0)
            nw, nh = int(iw*sc), int(ih*sc)
            bmp = wx.Bitmap(img.Scale(nw, nh, wx.IMAGE_QUALITY_HIGH))
        except Exception:
            return
        # Reuse existing preview dialog if still open
        parent = self.GetTopLevelParent()
        old_dlg = getattr(parent, '_preview_dlg', None)
        if old_dlg and (not hasattr(old_dlg, 'IsDestroyed') or not old_dlg.IsDestroyed()):
            old_dlg = parent._preview_dlg
            old_sb = getattr(parent, '_preview_sb', None)
            if old_sb and old_sb.IsOk() and old_sb.IsAlive():
                new_bmp = wx.Bitmap(img.Scale(nw, nh, wx.IMAGE_QUALITY_HIGH))
                old_sb.SetBitmap(new_bmp)
                old_dlg.Raise()
                old_dlg.Fit()
                old_dlg.Layout()
                return
        # Create new preview dialog
        self._new_preview(parent, nw, nh, bmp)

    def _new_preview(self, parent, nw, nh, bmp):
        dlg = wx.Dialog(parent, title=T("preview_title"),
                        style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        mp = wx.Panel(dlg)
        s = wx.BoxSizer(wx.VERTICAL)
        sb = wx.StaticBitmap(mp, bitmap=bmp)
        s.Add(sb, 1, wx.EXPAND|wx.ALL, 10)
        mp.SetSizer(s)
        dlg.SetClientSize((nw+20, nh+70))
        dlg.CentreOnParent()
        parent._preview_dlg = dlg
        parent._preview_sb = sb
        dlg.Show()
        dlg.Bind(wx.EVT_CLOSE, lambda e: (
            parent.__setattr__('_preview_dlg', None),
            parent.__setattr__('_preview_sb', None),
            dlg.Destroy()))

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

def _base64_encode(key):
    """Simple obfuscation for API key storage."""
    if not key:
        return ""
    return base64.b64encode(key.encode()).decode()

def _base64_decode(encoded):
    """Decode obfuscated API key."""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return ""

class SchAiAssistantDialog(wx.Dialog):
    def __init__(self, parent, plugin_dir):
        super().__init__(parent, title=T("title"), size=(1100,750),
                         style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER|wx.MAXIMIZE_BOX|wx.MINIMIZE_BOX)
        self.plugin_dir = plugin_dir
        # Load plugin icon
        _icon_path = os.path.join(self.plugin_dir, "icon.png")
        if os.path.exists(_icon_path):
            self.SetIcon(wx.Icon(_icon_path, wx.BITMAP_TYPE_PNG))
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
        """Create the settings dialog with API and Symbol settings."""
        self.settings_dlg = wx.Dialog(self, title=T("settings_title"),
            style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.settings_dlg.SetSize((420, 700))
        pan = wx.Panel(self.settings_dlg)
        sz = wx.BoxSizer(wx.VERTICAL)

        # ── API Settings Section ──
        ab = wx.StaticBox(pan, label=T("api_settings"))
        a_sz = wx.StaticBoxSizer(ab, wx.VERTICAL)

        # Model: editable dropdown with presets (select a preset or type a custom name)
        a_sz.Add(wx.StaticText(ab, label=T("model")+":"), 0, wx.TOP|wx.LEFT, 6)
        self.model_choice = wx.ComboBox(ab, value="agnes-2.5-flash",
                                        choices=list(MODEL_PRESETS.keys()))
        self.model_choice.SetToolTip(T("model_hint"))
        self.model_choice.Bind(wx.EVT_COMBOBOX, self._on_model_change)
        a_sz.Add(self.model_choice, 0, wx.EXPAND|wx.ALL, 6)

        a_sz.Add(wx.StaticText(ab, label=T("endpoint")+":"), 0, wx.TOP|wx.LEFT, 6)
        endpoint_choices = list(dict.fromkeys([p["endpoint"] for p in MODEL_PRESETS.values()]))
        self.endpoint_ctrl = wx.ComboBox(ab, value=MODEL_PRESETS["agnes-2.5-flash"]["endpoint"],
                                         choices=endpoint_choices)
        self.endpoint_ctrl.SetToolTip(T("endpoint_hint"))
        a_sz.Add(self.endpoint_ctrl, 0, wx.EXPAND|wx.ALL, 6)

        # API Key (editable dropdown with presets, masked display)
        a_sz.Add(wx.StaticText(ab, label=T("api_key")+":"), 0, wx.TOP|wx.LEFT, 6)
        # Create masked presets for display
        api_key_presets_raw = [MODEL_PRESETS[m]["api_key"] for m in MODEL_PRESETS if MODEL_PRESETS[m]["api_key"]]
        def _mask_key(k):
            return k[:6] + "•" * (len(k) - 10) + k[-4:] if len(k) > 10 else "•" * len(k)
        api_key_presets = [_mask_key(k) for k in api_key_presets_raw]
        self.api_key_ctrl = wx.ComboBox(ab, value=self.api_key if self.api_key else (api_key_presets[0] if api_key_presets else ""),
                                        choices=api_key_presets if api_key_presets else ["(输入自定义 API Key)"])
        self.api_key_ctrl.SetToolTip(T("api_key_hint"))
        self._mask_api_key()  # Mask the display
        self.api_key_ctrl.Bind(wx.EVT_TEXT, self._on_api_key_change)
        a_sz.Add(self.api_key_ctrl, 0, wx.EXPAND|wx.ALL, 6)
        # Free key and Save button on same row
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        free_btn = wx.Button(ab, label=T("free_key"), size=(100, -1))
        free_btn.Bind(wx.EVT_BUTTON, lambda e: __import__('webbrowser').open("https://agnes-ai.cn/settings/apiKeys"))
        btn_row.Add(free_btn, 0, wx.RIGHT, 6)
        save_api_btn = wx.Button(ab, label=T("save_key"))
        save_api_btn.Bind(wx.EVT_BUTTON, self._on_save_api)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(save_api_btn, 0)
        a_sz.Add(btn_row, 0, wx.EXPAND|wx.RIGHT|wx.LEFT, 6)


        sz.Add(a_sz, 0, wx.EXPAND|wx.ALL, 8)

        # ── Symbol Settings Section ──
        sb = wx.StaticBox(pan, label=T("symbol_settings"))
        s_sz = wx.StaticBoxSizer(sb, wx.VERTICAL)

        s_sz.Add(wx.StaticText(sb, label=T("symbol_name")+":"), 0, wx.TOP|wx.LEFT, 6)
        self.sym_name_ctrl = wx.TextCtrl(sb, value="NEW_CHIP")
        s_sz.Add(self.sym_name_ctrl, 0, wx.EXPAND|wx.ALL, 4)

        s_sz.Add(wx.StaticText(sb, label=T("ref_prefix")+":"), 0, wx.TOP|wx.LEFT, 6)
        self.ref_prefix_ctrl = wx.TextCtrl(sb, value="U")
        s_sz.Add(self.ref_prefix_ctrl, 0, wx.EXPAND|wx.ALL, 4)

        s_sz.Add(wx.StaticText(sb, label=T("pin_length")), 0, wx.TOP|wx.LEFT, 6)
        self.pin_len_ctrl = wx.SpinCtrlDouble(sb, value="2.54", min=1.0, max=20.0, inc=0.5)
        self.pin_len_ctrl.SetDigits(2)
        s_sz.Add(self.pin_len_ctrl, 0, wx.EXPAND|wx.ALL, 4)

        s_sz.Add(wx.StaticText(sb, label=T("pin_spacing")), 0, wx.TOP|wx.LEFT, 6)
        self.pin_spacing_ctrl = wx.SpinCtrlDouble(sb, value="2.54", min=1.0, max=20.0, inc=0.5)
        self.pin_spacing_ctrl.SetDigits(2)
        s_sz.Add(self.pin_spacing_ctrl, 0, wx.EXPAND|wx.ALL, 4)

        self.show_numbers_cb = wx.CheckBox(sb, label=T("show_numbers"))
        self.show_numbers_cb.SetValue(True)
        s_sz.Add(self.show_numbers_cb, 0, wx.LEFT|wx.BOTTOM, 8)

        self.show_names_cb = wx.CheckBox(sb, label=T("show_names"))
        self.show_names_cb.SetValue(True)
        s_sz.Add(self.show_names_cb, 0, wx.LEFT|wx.BOTTOM, 8)
        sz.Add(s_sz, 0, wx.EXPAND|wx.ALL, 8)

        # ── Dialog Buttons ──
        bb = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(pan, wx.ID_OK, T("ok"))
        cancel_btn = wx.Button(pan, wx.ID_CANCEL, T("cancel"))
        bb.AddButton(ok_btn)
        bb.AddButton(cancel_btn)
        bb.Realize()
        ok_btn.Bind(wx.EVT_BUTTON, lambda e: self.settings_dlg.EndModal(0))
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.settings_dlg.EndModal(0))
        sz.Add(bb, 0, wx.EXPAND|wx.ALL, 8)

        pan.SetSizer(sz)

    def _on_model_change(self, event):
        """Auto-update endpoint and api_key when a preset is selected."""
        name = self.model_choice.GetValue().strip()
        if name in MODEL_PRESETS:
            preset = MODEL_PRESETS[name]
            self.endpoint_ctrl.SetValue(preset["endpoint"])
            # Load key for this model from stored settings
            stored_key = self._load_model_api_key(name)
            self._current_api_key = stored_key
            self.api_key_ctrl.SetValue(self._mask_key_display(stored_key))
            # Mark as not user-entered since we just loaded it
            if hasattr(self, '_user_entered_key'):
                delattr(self, '_user_entered_key')

    def _on_api_key_change(self, event):
        """Handle API key input: mask as user types and mark as user-entered."""
        key = self.api_key_ctrl.GetValue()
        # Check if this is different from all preset masks (meaning user typed something new)
        is_custom = not any(
            self._mask_key_display(p["api_key"]) == key 
            for p in MODEL_PRESETS.values()
        )
        if is_custom:
            self._user_entered_key = True
        self._current_api_key = key  # Store raw key
        self.api_key_ctrl.SetValue(self._mask_key_display(key))

    def _mask_key_display(self, key):
        """Return masked version of API key for display."""
        if len(key) > 10:
            return key[:6] + "•" * (len(key) - 10) + key[-4:]
        return "•" * len(key)

    def _mask_api_key(self):
        """Mask API key display: show first 6 and last 4 chars."""
        if hasattr(self, '_current_api_key'):
            self.api_key_ctrl.SetValue(self._mask_key_display(self._current_api_key))
        else:
            key = self.api_key_ctrl.GetValue()
            self.api_key_ctrl.SetValue(self._mask_key_display(key))

    def _on_save_api(self, event):
        """Save API settings to settings.json (per-model with base64 encoding)."""
        self.api_key = getattr(self, '_current_api_key', '').strip()
        # Reset user-entered flag after save
        if hasattr(self, '_user_entered_key'):
            delattr(self, '_user_entered_key')
        try:
            settings_path = os.path.join(self.plugin_dir, "settings.json")
            settings = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            # Get current model name
            current_model = self.model_choice.GetValue().strip()
            # Save current model's key with base64 encoding
            settings[current_model] = {
                "api_key": self._base64_encode(self.api_key)
            }
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
            wx.MessageBox(T("api_saved"), "Settings", wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(str(e), "Error", wx.ICON_ERROR)

    def _on_settings(self, event):
        """Open settings dialog."""
        self.settings_dlg.ShowModal()

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
            endpoint = self.endpoint_ctrl.GetValue().strip() or "https://api.agnes-ai.cn/v1/chat/completions"
            model = self.model_choice.GetValue().strip() or "agnes-2.5-flash"
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
            endpoint = self.endpoint_ctrl.GetValue().strip() or "https://api.agnes-ai.cn/v1/chat/completions"
            model = self.model_choice.GetValue().strip() or "agnes-2.5-flash"
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
                return json.load(f).get("api_key", "sk-H6dvNuYBnFoRapkiRjvX06xvewuIjqXV3rlaxUTfZIsjNHty")
        except Exception: return ""
