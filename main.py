import os
import sys
import json
import shutil
import random
import threading
import urllib.request
from pathlib import Path

from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.metrics import dp
from kivy.properties import (
    StringProperty, BooleanProperty, NumericProperty, ListProperty
)
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.image import Image as KivyImage

from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton, MDRaisedButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivymd.uix.list import (
    MDList, OneLineListItem, TwoLineListItem,
    ThreeLineListItem
)
from kivymd.uix.dialog import MDDialog
from kivymd.uix.spinner import MDSpinner
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.slider import MDSlider

try:
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path
    IS_ANDROID = True
except ImportError:
    IS_ANDROID = False

AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac")


def get_storage_path():
    if IS_ANDROID:
        try:
            return primary_external_storage_path()
        except Exception:
            pass
    return str(Path.home())


BASE_DIR = get_storage_path()
APP_DIR = os.path.join(BASE_DIR, "Toca")
DOWNLOADS_DIR = os.path.join(APP_DIR, "Downloads")
COVERS_DIR = os.path.join(APP_DIR, "Covers")
LIBRARY_FILE = os.path.join(APP_DIR, "library.json")


def ensure_dirs():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(COVERS_DIR, exist_ok=True)


def load_library():
    if os.path.exists(LIBRARY_FILE):
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_library(library):
    ensure_dirs()
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)


class CoverDownloader(threading.Thread):
    def __init__(self, url, title, callback):
        super().__init__(daemon=True)
        self.url = url
        self.title = title
        self.callback = callback

    def run(self):
        try:
            if not self.url:
                Clock.schedule_once(lambda dt: self.callback(""))
                return
            safe = "".join(
                c for c in self.title if c.isalnum() or c in (" ", "-", "_")
            ).strip().replace(" ", "_")[:60]
            local = os.path.join(COVERS_DIR, f"{safe}.jpg")
            if os.path.exists(local):
                Clock.schedule_once(lambda dt: self.callback(local))
                return
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(local, "wb") as f:
                f.write(data)
            Clock.schedule_once(lambda dt: self.callback(local))
        except Exception:
            Clock.schedule_once(lambda dt: self.callback(""))


class FolderScanThread(threading.Thread):
    def __init__(self, folder_path, callback):
        super().__init__(daemon=True)
        self.folder_path = folder_path
        self.callback = callback

    def run(self):
        found = []
        try:
            for root, dirs, files in os.walk(self.folder_path):
                for f in files:
                    if f.lower().endswith(AUDIO_EXTENSIONS):
                        full = os.path.join(root, f)
                        name = os.path.splitext(f)[0]
                        found.append({"path": full, "name": name})
                if len(found) >= 500:
                    break
        except Exception:
            pass
        Clock.schedule_once(lambda dt: self.callback(found))


class TocaMobileApp(MDApp):
    library = ListProperty([])
    current_index = NumericProperty(-1)
    is_playing = BooleanProperty(False)
    is_shuffle = BooleanProperty(False)
    is_repeat = BooleanProperty(False)
    is_circular = BooleanProperty(False)
    current_title = StringProperty("Nenhuma faixa selecionada")
    current_status = StringProperty("Toca Mobile")
    current_cover = StringProperty("")

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Orange"
        self.theme_cls.primary_hue = "700"
        self.title = "Toca Mobile"
        ensure_dirs()
        self.library = load_library()
        self.sound = None
        self._progress_event = None

        if IS_ANDROID:
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.MANAGE_EXTERNAL_STORAGE,
                Permission.INTERNET,
            ])
        return self.build_ui()

    def build_ui(self):
        root = MDBoxLayout(orientation="vertical")

        self.toolbar = MDTopAppBar(
            title="Toca Mobile",
            md_bg_color="#121212",
            specific_text_color="#FFFFFF",
            elevation=0,
        )
        root.add_widget(self.toolbar)

        self.screen_manager = ScreenManager(
            transition=SlideTransition(direction="left")
        )
        self.screen_manager.add_widget(self.build_library_screen())
        self.screen_manager.add_widget(self.build_import_screen())
        self.screen_manager.add_widget(self.build_favorites_screen())
        self.screen_manager.add_widget(self.build_downloads_screen())

        root.add_widget(self.screen_manager)
        root.add_widget(self.build_player_bar())

        bottom_nav = MDBottomNavigation(
            panel_color="#121212",
            text_color_active="#FF6B00",
            text_color_normal="#B3B3B3",
        )

        nav_library = MDBottomNavigationItem(
            name="library", text="Biblioteca", icon="music"
        )
        nav_library.bind(on_press=lambda x: self.switch_screen("library"))
        bottom_nav.add_widget(nav_library)

        nav_import = MDBottomNavigationItem(
            name="import", text="Importar", icon="folder-plus"
        )
        nav_import.bind(on_press=lambda x: self.switch_screen("import"))
        bottom_nav.add_widget(nav_import)

        nav_favorites = MDBottomNavigationItem(
            name="favorites", text="Favoritos", icon="heart"
        )
        nav_favorites.bind(on_press=lambda x: self.switch_screen("favorites"))
        bottom_nav.add_widget(nav_favorites)

        nav_downloads = MDBottomNavigationItem(
            name="downloads", text="Offline", icon="download"
        )
        nav_downloads.bind(on_press=lambda x: self.switch_screen("downloads"))
        bottom_nav.add_widget(nav_downloads)

        root.add_widget(bottom_nav)
        return root

    def build_library_screen(self):
        screen = Screen(name="library")
        layout = MDBoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))

        header = MDLabel(
            text="A Minha Biblioteca",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            font_style="H6",
            size_hint_y=None,
            height=dp(40),
        )
        layout.add_widget(header)

        self.library_list = MDList()
        scroll = ScrollView()
        scroll.add_widget(self.library_list)
        layout.add_widget(scroll)
        screen.add_widget(layout)
        return screen

    def build_import_screen(self):
        screen = Screen(name="import")
        layout = MDBoxLayout(
            orientation="vertical", padding=dp(16), spacing=dp(16),
        )

        title = MDLabel(
            text="Importar Músicas",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            font_style="H6",
            size_hint_y=None,
            height=dp(40),
        )
        layout.add_widget(title)

        subtitle = MDLabel(
            text="Seleciona ficheiros de áudio do teu telemóvel",
            theme_text_color="Custom",
            text_color="#B3B3B3",
            font_style="Body2",
            size_hint_y=None,
            height=dp(30),
        )
        layout.add_widget(subtitle)

        btn_single = MDRaisedButton(
            text="Selecionar Ficheiros de Áudio",
            md_bg_color="#FF6B00",
            text_color="#FFFFFF",
            size_hint_x=1,
            on_release=self.pick_audio_files,
        )
        layout.add_widget(btn_single)

        btn_folder = MDRaisedButton(
            text="Importar Pasta Inteira",
            md_bg_color="#333333",
            text_color="#FFFFFF",
            size_hint_x=1,
            on_release=self.pick_folder,
        )
        layout.add_widget(btn_folder)

        self.import_spinner = MDSpinner(
            size_hint=(None, None),
            size=(dp(36), dp(36)),
            active=False,
        )
        layout.add_widget(self.import_spinner)

        self.import_status = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color="#B3B3B3",
            font_style="Caption",
            size_hint_y=None,
            height=dp(30),
        )
        layout.add_widget(self.import_status)

        self.import_list = MDList()
        scroll = ScrollView()
        scroll.add_widget(self.import_list)
        layout.add_widget(scroll)

        screen.add_widget(layout)
        return screen

    def build_favorites_screen(self):
        screen = Screen(name="favorites")
        layout = MDBoxLayout(orientation="vertical", padding=dp(8))

        header = MDLabel(
            text="Músicas Curtidas",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            font_style="H6",
            size_hint_y=None,
            height=dp(40),
        )
        layout.add_widget(header)

        self.favorites_list = MDList()
        scroll = ScrollView()
        scroll.add_widget(self.favorites_list)
        layout.add_widget(scroll)
        screen.add_widget(layout)
        return screen

    def build_downloads_screen(self):
        screen = Screen(name="downloads")
        layout = MDBoxLayout(orientation="vertical", padding=dp(8))

        header = MDLabel(
            text="Guardadas Offline",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            font_style="H6",
            size_hint_y=None,
            height=dp(40),
        )
        layout.add_widget(header)

        self.downloads_list = MDList()
        scroll = ScrollView()
        scroll.add_widget(self.downloads_list)
        layout.add_widget(scroll)
        screen.add_widget(layout)
        return screen

    def build_player_bar(self):
        bar = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(110),
            padding=[dp(12), dp(6), dp(12), dp(6)],
            md_bg_color="#181818",
        )

        info_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(10),
        )

        self.player_cover = KivyImage(
            source="",
            size_hint=(None, None),
            size=(dp(48), dp(48)),
            allow_stretch=True,
        )
        info_row.add_widget(self.player_cover)

        text_col = MDBoxLayout(orientation="vertical", spacing=dp(2))
        self.player_title_label = MDLabel(
            text="Nenhuma faixa selecionada",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            font_style="Caption",
            bold=True,
            size_hint_y=0.6,
        )
        self.player_status_label = MDLabel(
            text="Toca Mobile",
            theme_text_color="Custom",
            text_color="#B3B3B3",
            font_style="Caption",
            size_hint_y=0.4,
        )
        text_col.add_widget(self.player_title_label)
        text_col.add_widget(self.player_status_label)
        info_row.add_widget(text_col)
        bar.add_widget(info_row)

        progress_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(32),
            spacing=dp(6),
        )
        self.pos_label = MDLabel(
            text="0:00", theme_text_color="Custom", text_color="#A7A7A7",
            font_style="Caption", size_hint_x=None, width=dp(40),
        )
        self.progress_slider = MDSlider(
            min=0, max=100, value=0,
            size_hint_x=1,
            color="#FF6B00",
            thumb_color="#FFFFFF",
        )
        self.progress_slider.bind(value=self.on_seek)
        self.dur_label = MDLabel(
            text="0:00", theme_text_color="Custom", text_color="#A7A7A7",
            font_style="Caption", size_hint_x=None, width=dp(40),
        )
        progress_row.add_widget(self.pos_label)
        progress_row.add_widget(self.progress_slider)
        progress_row.add_widget(self.dur_label)
        bar.add_widget(progress_row)

        controls_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(4),
            adaptive_width=True,
            pos_hint={"center_x": 0.5},
        )

        self.btn_shuffle = MDIconButton(
            icon="shuffle", theme_text_color="Custom", text_color="#B3B3B3"
        )
        self.btn_shuffle.bind(on_release=lambda x: self.toggle_shuffle())

        self.btn_prev = MDIconButton(
            icon="skip-previous", theme_text_color="Custom", text_color="#B3B3B3"
        )
        self.btn_prev.bind(on_release=lambda x: self.prev_track())

        self.btn_play = MDIconButton(
            icon="play",
            theme_text_color="Custom",
            text_color="#FFFFFF",
            md_bg_color="#FF6B00",
            icon_size=dp(30),
        )
        self.btn_play.bind(on_release=lambda x: self.toggle_play())

        self.btn_next = MDIconButton(
            icon="skip-next", theme_text_color="Custom", text_color="#B3B3B3"
        )
        self.btn_next.bind(on_release=lambda x: self.next_track())

        self.btn_repeat = MDIconButton(
            icon="repeat", theme_text_color="Custom", text_color="#B3B3B3"
        )
        self.btn_repeat.bind(on_release=lambda x: self.toggle_repeat())

        self.btn_circular = MDIconButton(
            icon="restart", theme_text_color="Custom", text_color="#B3B3B3"
        )
        self.btn_circular.bind(on_release=lambda x: self.toggle_circular())

        controls_row.add_widget(self.btn_shuffle)
        controls_row.add_widget(self.btn_prev)
        controls_row.add_widget(self.btn_play)
        controls_row.add_widget(self.btn_next)
        controls_row.add_widget(self.btn_repeat)
        controls_row.add_widget(self.btn_circular)
        bar.add_widget(controls_row)

        return bar

    def switch_screen(self, name):
        self.screen_manager.current = name
        refresh_map = {
            "library": self.refresh_library_list,
            "favorites": self.refresh_favorites_list,
            "downloads": self.refresh_downloads_list,
        }
        if name in refresh_map:
            refresh_map[name]()

    def refresh_library_list(self):
        self.library_list.clear_widgets()
        if not self.library:
            self.library_list.add_widget(
                OneLineListItem(text="Nenhuma música. Toca em Importar!")
            )
            return
        for i, track in enumerate(self.library):
            fav = "[color=FF6B00]♥ [/color]" if track.get("favorite") else ""
            playing = " [color=FF6B00]▶[/color]" if i == self.current_index else ""
            item = ThreeLineListItem(
                text=f"{fav}{track['name']}{playing}",
                secondary_text=track.get("duration_str", "Local"),
                tertiary_text=track.get("path", "")[-40:],
            )
            idx = i
            item.bind(on_release=lambda x, idx=idx: self.play_track(idx))
            self.library_list.add_widget(item)

    def refresh_favorites_list(self):
        self.favorites_list.clear_widgets()
        favs = [t for t in self.library if t.get("favorite")]
        if not favs:
            self.favorites_list.add_widget(
                OneLineListItem(text="Nenhuma música favorita")
            )
            return
        for track in favs:
            idx = self.library.index(track)
            item = TwoLineListItem(
                text=track["name"],
                secondary_text=track.get("duration_str", "Local"),
            )
            item.bind(on_release=lambda x, idx=idx: self.play_track(idx))
            self.favorites_list.add_widget(item)

    def refresh_downloads_list(self):
        self.downloads_list.clear_widgets()
        offline = [t for t in self.library if t.get("is_downloaded")]
        if not offline:
            self.downloads_list.add_widget(
                OneLineListItem(text="Nenhuma música guardada")
            )
            return
        for track in offline:
            idx = self.library.index(track)
            item = TwoLineListItem(
                text=track["name"],
                secondary_text=track.get("duration_str", "Local"),
            )
            item.bind(on_release=lambda x, idx=idx: self.play_track(idx))
            self.downloads_list.add_widget(item)

    def pick_audio_files(self, *args):
        if IS_ANDROID:
            self._pick_files_android()
        else:
            self._pick_files_desktop()

    def _pick_files_android(self):
        try:
            from android import activity
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("audio/*")
            intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)
            activity.startActivityForResult(intent, 1)
        except Exception as e:
            self.import_status.text = f"Erro: {str(e)[:60]}"

    def _pick_files_desktop(self):
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self._on_file_selected,
                filters=["*.mp3", "*.m4a", "*.wav", "*.ogg", "*.flac", "*.aac"],
            )
        except ImportError:
            self.import_status.text = (
                f"Seleciona ficheiros em:\n{DOWNLOADS_DIR}"
            )

    def _on_file_selected(self, selection):
        if selection:
            for path in selection:
                self._import_single_file(path)

    def pick_folder(self, *args):
        if IS_ANDROID:
            self._pick_folder_android()
        else:
            self._scan_folder(DOWNLOADS_DIR)

    def _pick_folder_android(self):
        try:
            from android import activity
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
            )
            activity.startActivityForResult(intent, 2)
        except Exception as e:
            self.import_status.text = f"Erro: {str(e)[:60]}"

    def _scan_folder(self, folder_path):
        self.import_status.text = f"A procurar em: {os.path.basename(folder_path)}..."
        self.import_spinner.active = True
        self.import_list.clear_widgets()
        FolderScanThread(folder_path, self._on_folder_scanned).start()

    def _on_folder_scanned(self, found_files):
        self.import_spinner.active = False
        self.import_list.clear_widgets()

        if not found_files:
            self.import_status.text = "Nenhum ficheiro de áudio encontrado"
            return

        self.import_status.text = f"Encontrados {len(found_files)}. A importar..."
        imported = 0
        for item in found_files:
            path = item["path"]
            name = item["name"]

            already = any(
                t.get("original_path") == path or t.get("path") == path
                for t in self.library
            )
            if already:
                continue

            dest = os.path.join(DOWNLOADS_DIR, os.path.basename(path))
            if not os.path.exists(dest):
                try:
                    shutil.copy2(path, dest)
                except Exception:
                    continue

            self.library.append({
                "path": dest,
                "name": name,
                "favorite": False,
                "is_online": False,
                "is_downloaded": True,
                "original_path": path,
                "duration_str": "Local",
                "cover_path": "",
            })
            imported += 1
            self.import_list.add_widget(OneLineListItem(text=name))

        save_library(self.library)
        self.import_status.text = f"Importadas {imported} músicas!"
        self.refresh_library_list()

    def _import_single_file(self, source_path):
        self.import_status.text = "A importar..."
        self.import_spinner.active = True

        def on_done(success, result):
            self.import_spinner.active = False
            if success:
                name = os.path.splitext(os.path.basename(source_path))[0]
                already = any(
                    t.get("original_path") == source_path or t.get("path") == result
                    for t in self.library
                )
                if not already:
                    self.library.append({
                        "path": result,
                        "name": name,
                        "favorite": False,
                        "is_online": False,
                        "is_downloaded": True,
                        "original_path": source_path,
                        "duration_str": "Local",
                        "cover_path": "",
                    })
                    save_library(self.library)
                    self.refresh_library_list()
                    self.import_status.text = f"Importado: {name}"
                else:
                    self.import_status.text = f"Já existe: {name}"
            else:
                self.import_status.text = f"Erro: {str(result)[:60]}"

        def copy_file():
            try:
                filename = os.path.basename(source_path)
                dest = os.path.join(DOWNLOADS_DIR, filename)
                if not os.path.exists(dest):
                    shutil.copy2(source_path, dest)
                Clock.schedule_once(lambda dt: on_done(True, dest))
            except Exception as e:
                Clock.schedule_once(lambda dt: on_done(False, str(e)))

        threading.Thread(target=copy_file, daemon=True).start()

    def handle_android_result(self, request_code, result_code, data):
        if request_code == 1 and data is not None:
            clip_data = data.getClipData()
            if clip_data:
                for i in range(clip_data.getItemCount()):
                    uri = clip_data.getItemAt(i).getUri()
                    self._import_from_uri(uri)
            else:
                uri = data.getData()
                if uri:
                    self._import_from_uri(uri)
        elif request_code == 2 and data is not None:
            tree_uri = data.getData()
            if tree_uri:
                self.import_status.text = "Pasta selecionada. A importar..."
                self.import_spinner.active = True
                self._scan_document_tree(tree_uri)

    def _import_from_uri(self, uri):
        try:
            from jnius import autoclass

            Context = autoclass("android.content.Context")
            resolver = Context.getApplication().getContentResolver()

            cursor = resolver.query(uri, None, None, None, None)
            name = "imported_audio"
            if cursor:
                if cursor.moveToFirst():
                    idx = cursor.getColumnIndex("_display_name")
                    if idx >= 0:
                        name = cursor.getString(idx)
                cursor.close()

            input_stream = resolver.openInputStream(uri)
            dest = os.path.join(DOWNLOADS_DIR, name)
            with open(dest, "wb") as f:
                shutil.copyfileobj(input_stream, f)
            input_stream.close()

            already = any(t.get("path") == dest for t in self.library)
            if not already:
                clean_name = os.path.splitext(name)[0]
                self.library.append({
                    "path": dest,
                    "name": clean_name,
                    "favorite": False,
                    "is_online": False,
                    "is_downloaded": True,
                    "duration_str": "Local",
                    "cover_path": "",
                })
                save_library(self.library)
                self.refresh_library_list()
                self.import_status.text = f"Importado: {clean_name}"
        except Exception as e:
            self.import_status.text = f"Erro: {str(e)[:60]}"

    def _scan_document_tree(self, tree_uri):
        try:
            from jnius import autoclass

            ContentResolver = autoclass("android.content.ContentResolver")
            resolver = ContentResolver.getContentResolver()
            cursor = resolver.query(
                tree_uri, None, None, None, None
            )
            if cursor and cursor.moveToFirst():
                name_idx = cursor.getColumnIndex("document_id")
                if name_idx >= 0:
                    doc_id = cursor.getString(name_idx)
                    self.import_status.text = f"Doc: {doc_id}"
                cursor.close()
        except Exception as e:
            self.import_status.text = f"Erro scan: {str(e)[:60]}"

    def play_track(self, index):
        if index < 0 or index >= len(self.library):
            return
        self.current_index = index
        track = self.library[index]
        self.current_title = track["name"]
        self.player_title_label.text = track["name"]

        path = track.get("path", "")
        if not path or not os.path.exists(path):
            alt = os.path.join(DOWNLOADS_DIR, os.path.basename(path))
            if os.path.exists(alt):
                path = alt
                track["path"] = alt
            else:
                self.current_status = "Ficheiro não encontrado"
                self.player_status_label.text = "Ficheiro não encontrado"
                return

        self.current_status = "A reproduzir..."
        self.player_status_label.text = "A reproduzir..."
        self.play_local(path)

        cover = track.get("cover_path", "")
        if cover and os.path.exists(cover):
            self.player_cover.source = cover
            self.current_cover = cover
        elif cover and cover.startswith("http"):
            CoverDownloader(
                cover, track["name"], self.on_cover_downloaded
            ).start()

        self.refresh_library_list()

    def play_local(self, path):
        if self.sound:
            self.sound.stop()
        try:
            self.sound = SoundLoader.load(path)
            if self.sound:
                self.sound.bind(on_stop=self.on_sound_stopped)
                self.sound.play()
                self.is_playing = True
                self.btn_play.icon = "pause"
                self.start_progress_tracking()
            else:
                self.current_status = "Formato não suportado"
                self.player_status_label.text = "Formato não suportado"
        except Exception as e:
            self.current_status = f"Erro: {str(e)[:50]}"
            self.player_status_label.text = self.current_status

    def on_sound_stopped(self):
        self.is_playing = False
        self.btn_play.icon = "play"
        if self.is_repeat and self.current_index >= 0:
            self.play_track(self.current_index)
        elif not self.is_repeat:
            self.next_track()

    def toggle_play(self):
        if not self.sound:
            if self.library:
                self.play_track(
                    0 if self.current_index < 0 else self.current_index
                )
            return
        if self.is_playing:
            self.sound.stop()
            self.is_playing = False
            self.btn_play.icon = "play"
        else:
            self.sound.play()
            self.is_playing = True
            self.btn_play.icon = "pause"

    def next_track(self):
        if not self.library:
            return
        if self.is_shuffle:
            choices = [
                i for i in range(len(self.library))
                if i != self.current_index
            ] if len(self.library) > 1 else [0]
            idx = random.choice(choices)
        else:
            idx = self.current_index + 1
            if idx >= len(self.library):
                if self.is_circular:
                    idx = 0
                else:
                    self.is_playing = False
                    self.btn_play.icon = "play"
                    return
        self.play_track(idx)

    def prev_track(self):
        if not self.library:
            return
        if self.sound and self.sound.get_pos() > 3:
            self.sound.seek(0)
            return
        idx = self.current_index - 1
        if idx < 0:
            idx = len(self.library) - 1 if self.is_circular else 0
        self.play_track(idx)

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        self.btn_shuffle.text_color = "#FF6B00" if self.is_shuffle else "#B3B3B3"

    def toggle_repeat(self):
        self.is_repeat = not self.is_repeat
        self.btn_repeat.text_color = "#FF6B00" if self.is_repeat else "#B3B3B3"

    def toggle_circular(self):
        self.is_circular = not self.is_circular
        self.btn_circular.text_color = (
            "#FF6B00" if self.is_circular else "#B3B3B3"
        )

    def toggle_favorite(self, index):
        if 0 <= index < len(self.library):
            self.library[index]["favorite"] = not self.library[index].get(
                "favorite", False
            )
            save_library(self.library)
            self.refresh_library_list()
            self.refresh_favorites_list()

    def delete_track(self, index):
        if 0 <= index < len(self.library):
            if self.current_index == index and self.sound:
                self.sound.stop()
                self.current_index = -1
            self.library.pop(index)
            save_library(self.library)
            current = self.screen_manager.current
            self.switch_screen(current)

    def start_progress_tracking(self):
        if self._progress_event:
            Clock.unschedule(self._progress_event)
        self._progress_event = Clock.schedule_interval(self.update_progress, 0.5)

    def update_progress(self, dt):
        if self.sound and self.is_playing:
            pos = self.sound.get_pos()
            dur = self.sound.length
            self.pos_label.text = self.format_time(pos)
            self.dur_label.text = self.format_time(dur)
            if dur > 0 and not self.progress_slider.is_active:
                self.progress_slider.value = (pos / dur) * 100

    def on_seek(self, instance, value):
        if self.sound and self.sound.length > 0:
            self.sound.seek(value / 100 * self.sound.length)

    def on_cover_downloaded(self, path):
        if path and os.path.exists(path):
            self.player_cover.source = path
            self.current_cover = path
            if 0 <= self.current_index < len(self.library):
                self.library[self.current_index]["cover_path"] = path
                save_library(self.library)

    @staticmethod
    def format_time(seconds):
        if seconds < 0:
            return "0:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"


if __name__ == "__main__":
    TocaMobileApp().run()
