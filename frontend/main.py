import flet as ft
import requests
import json
from datetime import datetime

API_BASE_URL = "https://3rkls769-5001.use.devtunnels.ms/api"

class ChatBubble(ft.Row):
    def __init__(self, author: str, text: str, is_me: bool):
        super().__init__()
        bubble = ft.Container(
            content=ft.Column([
                ft.Text(author, weight=ft.FontWeight.BOLD, size=12),
                ft.Text(text, selectable=True),
            ], spacing=4, tight=True),
            padding=ft.padding.all(12),
            border_radius=ft.border_radius.all(15),
        )
        
        if is_me:
            bubble.bgcolor = "primaryContainer"
            self.alignment = ft.MainAxisAlignment.END
        else:
            bubble.bgcolor = "surfaceVariant"
            self.alignment = ft.MainAxisAlignment.START
        
        self.controls = [bubble]

class NoteSharingApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "PeerStudy"
        self.page.window_width = 1000; self.page.window_height = 700
        self.page.theme = ft.Theme(color_scheme_seed="indigo")
        self.page.dark_theme = ft.Theme(color_scheme_seed="indigo")
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        
        self.current_group_id = None; self.current_group_name = ""
        self.all_notes = []; self.all_meetups = []
        
        self.notes_list = ft.ListView(expand=True, spacing=10)
        self.meetups_list = ft.ListView(expand=True, spacing=10)
        self.chat_list = ft.ListView(expand=True, spacing=15, auto_scroll=True)
        self.dashboard_groups_list = ft.ListView(expand=True, spacing=10)
        self.group_fab = ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self.on_group_fab_click, tooltip="Add Item")
        self.chat_input_row = ft.Row(visible=False)
        self.group_tabs = ft.Tabs(selected_index=0, animation_duration=300, on_change=self.on_tab_change, expand=True)

        self.page.on_route_change = self.route_change
        self.page.on_view_pop = self.view_pop
        self.page.pubsub.subscribe(self.on_pubsub_message)
        self.page.go("/login")

    def api_call(self, method, endpoint, data=None):
        token = self.page.client_storage.get("auth_token")
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        headers['Content-Type'] = 'application/json'
        try:
            response = requests.request(method.upper(), url=f"{API_BASE_URL}{endpoint}", json=data, headers=headers)
            response.raise_for_status()
            return (response.json() if response.content else {"success": True}), None
        except requests.exceptions.RequestException as e:
            error_message = f"API Error: {e}"
            if e.response is not None:
                try: 
                    error_data = e.response.json()
                    error_message = error_data.get('message', error_data.get('msg', str(e)))
                except json.JSONDecodeError: pass
            return None, error_message

    def show_error_dialog(self, message: str):
        error_dialog = ft.AlertDialog(
            modal=True, title=ft.Text("Error"), content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=self.close_dialog)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.overlay.append(error_dialog)
        self.page.dialog = error_dialog
        error_dialog.open = True
        self.page.update()

    def show_success_snackbar(self, message: str):
        self.page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=ft.Colors.WHITE),
            bgcolor=ft.Colors.GREEN_600, duration=4000
        )
        self.page.snack_bar.open = True
        self.page.update()

    def close_dialog(self, e=None):
        if self.page.dialog:
            self.page.dialog.open = False
            self.page.update()
            if self.page.dialog in self.page.overlay:
                self.page.overlay.remove(self.page.dialog)
            self.page.dialog = None
            self.page.update()

    def on_pubsub_message(self, message):
        try:
            if int(message) == self.current_group_id:
                self.load_group_notes(); self.load_group_meetups(); self.load_group_chat()
        except (ValueError, TypeError) as e: print(f"Error processing pubsub message: {message}. Error: {e}")

    def get_group_view(self):
        new_chat_message = ft.TextField(hint_text="Type a message...", expand=True, on_submit=self.send_chat_message, border_radius=20)
        self.chat_input_row.controls = [new_chat_message, ft.IconButton(icon=ft.Icons.SEND_ROUNDED, on_click=self.send_chat_message, tooltip="Send Message")]
        search_notes_field = ft.TextField(hint_text="Search resources...", on_change=self.on_search_notes, border_radius=20, prefix_icon=ft.Icons.SEARCH)
        search_meetups_field = ft.TextField(hint_text="Search sessions...", on_change=self.on_search_meetups, border_radius=20, prefix_icon=ft.Icons.SEARCH)
        self.group_tabs.tabs = [
            ft.Tab(text="Resources", content=ft.Column([search_notes_field, self.notes_list], spacing=10, expand=True)),
            ft.Tab(text="Study Sessions", content=ft.Column([search_meetups_field, self.meetups_list], spacing=10, expand=True)),
            ft.Tab(text="Group Chat", content=self.chat_list)]
        main_column = ft.Column([self.group_tabs, self.chat_input_row], expand=True)
        return ft.View(f"/group/{self.current_group_id}", [
            ft.AppBar(title=ft.Text(self.current_group_name), bgcolor="surfaceVariant", 
                leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.page.go("/dashboard")),
                actions=[ft.IconButton(ft.Icons.LOGOUT, on_click=self.confirm_leave_group, tooltip="Leave Group", icon_color=ft.Colors.RED)]
            ), ft.Container(content=main_column, expand=True, padding=ft.padding.symmetric(horizontal=20))
        ], floating_action_button=self.group_fab)

    def _handle_leave_action(self, e):
        self.close_dialog()
        _, error = self.api_call('POST', f'/groups/{self.current_group_id}/leave')
        if not error:
            self.show_success_snackbar("You have left the group.")
            self.page.go("/dashboard")
        else:
            self.show_error_dialog(f"Failed to leave group: {error}")

    def confirm_leave_group(self, e):
        dialog = ft.AlertDialog(
            modal=True, title=ft.Text("Leave Group?"), content=ft.Text(f"Are you sure you want to leave '{self.current_group_name}'?"),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_dialog),
                ft.TextButton("Leave", on_click=self._handle_leave_action, style=ft.ButtonStyle(color=ft.Colors.RED))
            ], actions_alignment=ft.MainAxisAlignment.END
        )
        self.page.overlay.append(dialog)
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()
        
    def on_tab_change(self, e):
        is_chat_tab = (e.control.selected_index == 2)
        self.group_fab.visible = not is_chat_tab
        self.chat_input_row.visible = is_chat_tab
        self.page.update()

    def on_group_fab_click(self, e):
        active_tab_index = self.group_tabs.selected_index
        if active_tab_index == 0:
            self.page.go(f"/group/{self.current_group_id}/add-note")
        elif active_tab_index == 1:
            self.page.go(f"/group/{self.current_group_id}/add-meetup")

    def send_chat_message(self, e):
        if self.chat_input_row.controls:
            chat_message_field = self.chat_input_row.controls[0]
            if chat_message_field and chat_message_field.value:
                text = chat_message_field.value
                chat_message_field.value = ""; chat_message_field.focus()
                _, error = self.api_call('POST', f'/groups/{self.current_group_id}/chat', data={"text": text})
                if not error: self.page.pubsub.send_all(str(self.current_group_id))
                else: self.show_error_dialog(f"Failed to send: {error}")
                self.page.update()

    def on_search_notes(self, e):
        search_term = e.control.value.lower()
        if not search_term: self.populate_notes_list(self.all_notes)
        else: self.populate_notes_list([n for n in self.all_notes if search_term in n['title'].lower() or search_term in n['content'].lower()])

    def on_search_meetups(self, e):
        search_term = e.control.value.lower()
        if not search_term: self.populate_meetups_list(self.all_meetups)
        else: self.populate_meetups_list([m for m in self.all_meetups if search_term in m['topic'].lower() or (m.get('description') and search_term in m['description'].lower())])

    def populate_notes_list(self, notes_data):
        self.notes_list.controls.clear()
        if notes_data:
            for n in notes_data: self.notes_list.controls.append(ft.Card(ft.ListTile(title=ft.Text(n['title'], weight=ft.FontWeight.BOLD), subtitle=ft.Text(n['content']))))
        else: self.notes_list.controls.append(ft.Text("No resources found.", italic=True, text_align=ft.TextAlign.CENTER))
        self.page.update()

    def populate_meetups_list(self, meetups_data):
        self.meetups_list.controls.clear()
        if meetups_data:
            for m in meetups_data:
                time = datetime.fromisoformat(m['time']).astimezone().strftime('%A, %b %d @ %I:%M %p %Z')
                self.meetups_list.controls.append(ft.Card(ft.ListTile(leading=ft.Icon(ft.Icons.CALENDAR_MONTH), title=ft.Text(m['topic'], weight=ft.FontWeight.BOLD), subtitle=ft.Text(f"{time}\n{m['description']}"), trailing=ft.IconButton(ft.Icons.LINK, url=m['link'], disabled=not m['link'], tooltip="Join Meeting"))))
        else: self.meetups_list.controls.append(ft.Text("No study sessions found.", italic=True, text_align=ft.TextAlign.CENTER))
        self.page.update()

    def load_group_notes(self):
        self.all_notes, _ = self.api_call('GET', f'/groups/{self.current_group_id}/notes')
        self.populate_notes_list(self.all_notes or [])

    def load_group_meetups(self):
        self.all_meetups, _ = self.api_call('GET', f'/groups/{self.current_group_id}/meetups')
        self.populate_meetups_list(self.all_meetups or [])

    def load_group_chat(self):
        self.chat_list.controls.clear()
        data, _ = self.api_call('GET', f'/groups/{self.current_group_id}/chat')
        if data:
            current_username = self.page.client_storage.get("username")
            for msg in data: self.chat_list.controls.append(ChatBubble(author=msg['author'], text=msg['text'], is_me=(current_username == msg['author'])))
        self.page.update()

    def load_dashboard_groups(self):
        self.dashboard_groups_list.controls.clear()
        data, error = self.api_call('GET', '/groups')
        if error: self.show_error_dialog(error)
        elif data:
            for group in data:
                card_content = ft.Column([
                    ft.ListTile(leading=ft.Icon(ft.Icons.GROUP_WORK_OUTLINED), title=ft.Text(group['name'], weight=ft.FontWeight.BOLD), subtitle=ft.Text(f"{group['course_code']} - {group['member_count']} member(s)"), on_click=lambda _, g=group: self.on_group_click(g)),
                    ft.Container(content=ft.Row([ft.Text("Share Code:", weight=ft.FontWeight.W_500), ft.Text(group.get('join_code'), selectable=True, font_family="monospace"), ft.IconButton(ft.Icons.COPY, on_click=lambda _, c=group.get('join_code'): self.copy_to_clipboard(c), tooltip="Copy Code")], alignment=ft.MainAxisAlignment.END), padding=ft.padding.only(right=15, bottom=5))])
                self.dashboard_groups_list.controls.append(ft.Card(content=card_content))
        else: self.dashboard_groups_list.controls.append(ft.Container(content=ft.Column([
                ft.Icon(ft.Icons.GROUP_ADD_OUTLINED, size=60, color="onSurfaceVariant"),
                ft.Text("No study groups yet.", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Create a new group or join one with a code."),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), alignment=ft.alignment.center, expand=True))
        self.page.update()

    def get_dashboard_view(self):
        return ft.View("/dashboard", [
            ft.AppBar(title=ft.Text("Dashboard"), bgcolor="surfaceVariant",
                actions=[
                    ft.ElevatedButton("Join Group", icon=ft.Icons.LOGIN, on_click=lambda _: self.page.go("/join-group")),
                    ft.IconButton(ft.Icons.LOGOUT, on_click=self.logout, tooltip="Logout")
                ]
            ),
            ft.Container(
                content=ft.Column([
                    ft.Text("My Study Groups", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM), 
                    ft.Divider(), 
                    self.dashboard_groups_list
                ], expand=True, spacing=10), 
                padding=ft.padding.all(20), 
                expand=True
            )
        ], floating_action_button=ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=lambda _: self.page.go("/create-group"), tooltip="Create Group"))

    def get_add_note_view(self):
        title_field = ft.TextField(label="Resource Title", autofocus=True); content_field = ft.TextField(label="Content / Description / Link", multiline=True, min_lines=3)
        def add_click(e):
            if not title_field.value: return
            _, error = self.api_call('POST', f'/groups/{self.current_group_id}/notes', data={"title": title_field.value, "content": content_field.value})
            if not error: self.page.go(f"/group/{self.current_group_id}")
            else: self.show_error_dialog(error)
        return ft.View(f"/group/{self.current_group_id}/add-note", [ft.AppBar(title=ft.Text("Share Resource"), bgcolor="surfaceVariant", leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.page.go(f"/group/{self.current_group_id}"))), ft.Column([title_field, content_field, ft.FilledButton("Share", on_click=add_click)], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=20)])

    def get_add_meetup_view(self):
        topic_field = ft.TextField(label="Session Topic", autofocus=True); time_field = ft.TextField(label="Date & Time (e.g., 2024-12-25T14:30:00)", hint_text="ISO 8601 Format"); link_field = ft.TextField(label="Meeting Link (optional)"); desc_field = ft.TextField(label="Description (optional)", multiline=True)
        def add_click(e):
            if not all([topic_field.value, time_field.value]): return
            data = {"topic": topic_field.value, "time": time_field.value, "link": link_field.value, "description": desc_field.value}
            _, error = self.api_call('POST', f'/groups/{self.current_group_id}/meetups', data=data)
            if not error: self.page.go(f"/group/{self.current_group_id}")
            else: self.show_error_dialog(error)
        return ft.View(f"/group/{self.current_group_id}/add-meetup", [ft.AppBar(title=ft.Text("Schedule Session"), bgcolor="surfaceVariant", leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.page.go(f"/group/{self.current_group_id}"))), ft.Column([topic_field, time_field, link_field, desc_field, ft.FilledButton("Schedule", on_click=add_click)], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=20)])

    def copy_to_clipboard(self, text): 
        self.page.set_clipboard(text)
        self.show_success_snackbar("Copied to clipboard!")
    
    def get_create_group_view(self):
        name_field = ft.TextField(label="Group Name", autofocus=True); course_field = ft.TextField(label="Course/Topic"); desc_field = ft.TextField(label="Description", multiline=True)
        def create_click(e):
            if not name_field.value: return
            _, error = self.api_call('POST', '/groups', data={"name": name_field.value, "course_code": course_field.value, "description": desc_field.value})
            if not error: self.page.go("/dashboard")
            else: self.show_error_dialog(error)
        return ft.View("/create-group", [ft.AppBar(title=ft.Text("Create Group"), bgcolor="surfaceVariant", leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.page.go("/dashboard"))), ft.Column([name_field, course_field, desc_field, ft.FilledButton("Create", on_click=create_click)], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=20)])

    def get_join_group_view(self):
        code_field = ft.TextField(label="Enter Join Code", autofocus=True)
        def join_click(e):
            if not code_field.value: return
            result, error = self.api_call('POST', '/groups/join', data={"join_code": code_field.value})
            if result and not error: 
                self.show_success_snackbar(result.get("message"))
                self.page.go("/dashboard")
            else: self.show_error_dialog(error)
        return ft.View("/join-group", [ft.AppBar(title=ft.Text("Join Group"), bgcolor="surfaceVariant", leading=ft.IconButton(ft.Icons.ARROW_BACK, on_click=lambda _: self.page.go("/dashboard"))), ft.Column([code_field, ft.FilledButton("Join", on_click=join_click)], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True, spacing=20)])
    
    def get_login_view(self):
        username_field = ft.TextField(label="Username", autofocus=True); password_field = ft.TextField(label="Password", password=True, on_submit=lambda e: login_click(e))
        def login_click(e):
            if not all([username_field.value, password_field.value]): 
                self.show_error_dialog("Please enter both username and password.")
                return
            result, error = self.api_call('POST', '/login', data={"username": username_field.value, "password": password_field.value})
            if result and 'user_id' in result:
                self.page.client_storage.set("auth_token", result['access_token']); self.page.client_storage.set("user_id", result['user_id']); self.page.client_storage.set("username", username_field.value)
                self.show_success_snackbar("Login successful!")
                self.page.go("/dashboard")
            else: self.show_error_dialog(error or "Incorrect username or password.")
        return ft.View("/login", [
            ft.Column([
                ft.Text("PeerStudy", theme_style=ft.TextThemeStyle.HEADLINE_LARGE, color="primary"), 
                username_field, password_field, 
                ft.FilledButton("Login", on_click=login_click), 
                ft.TextButton("Register", on_click=lambda _: self.page.go("/register"))
            ], spacing=20, horizontal_alignment=ft.CrossAxisAlignment.CENTER, width=300)
        ], vertical_alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def get_register_view(self):
        username_field = ft.TextField(label="Username"); email_field = ft.TextField(label="Email"); password_field = ft.TextField(label="Password", password=True)
        def register_click(e):
            if not all([username_field.value, email_field.value, password_field.value]): 
                self.show_error_dialog("All fields are required.")
                return
            _, error = self.api_call('POST', '/register', data={"username": username_field.value, "email": email_field.value, "password": password_field.value})
            if not error: 
                self.show_success_snackbar("Registration successful! Please log in.")
                self.page.go("/login")
            else: self.show_error_dialog(error or "An unknown registration error occurred.")
        return ft.View("/register", [
            ft.Column([
                ft.Text("Create Account", theme_style=ft.TextThemeStyle.HEADLINE_LARGE, color="primary"), 
                username_field, email_field, password_field, 
                ft.FilledButton("Register", on_click=register_click), 
                ft.TextButton("Login", on_click=lambda _: self.page.go("/login"))
            ], spacing=20, horizontal_alignment=ft.CrossAxisAlignment.CENTER, width=300)
        ], vertical_alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    
    def on_group_click(self, group): self.current_group_id = group['id']; self.current_group_name = group['name']; self.page.go(f"/group/{self.current_group_id}")
    def logout(self, e): self.page.client_storage.clear(); self.page.go("/login")
    def route_change(self, route):
        self.page.views.clear()
        token = self.page.client_storage.get("auth_token")
        is_auth_route = self.page.route in ["/login", "/register"]
        base_view_added = False
        if token and not is_auth_route:
            self.page.views.append(self.get_dashboard_view()); base_view_added = True
        if self.page.route == "/login":
            if base_view_added: self.page.views.clear()
            self.page.views.append(self.get_login_view())
        elif self.page.route == "/register":
            if base_view_added: self.page.views.clear()
            self.page.views.append(self.get_register_view())
        elif token:
            self.group_fab.visible = True; self.chat_input_row.visible = False
            if self.page.route == "/dashboard": self.load_dashboard_groups()
            elif self.page.route == "/create-group": self.page.views.append(self.get_create_group_view())
            elif self.page.route == "/join-group": self.page.views.append(self.get_join_group_view())
            elif self.page.route.startswith("/group/"):
                parts = self.page.route.strip("/").split("/")
                self.current_group_id = int(parts[1])
                if not self.current_group_name or str(self.current_group_id) != parts[1]:
                    group_data, _ = self.api_call('GET', f'/groups/{self.current_group_id}')
                    if group_data: self.current_group_name = group_data.get('name', 'Group')
                self.page.views.append(self.get_group_view())
                if len(parts) > 2 and parts[2] == "add-note": self.page.views.append(self.get_add_note_view())
                elif len(parts) > 2 and parts[2] == "add-meetup": self.page.views.append(self.get_add_meetup_view())
                else: self.load_group_notes(); self.load_group_meetups(); self.load_group_chat()
        else: self.page.go("/login")
        self.page.update()

    def view_pop(self, view):
        self.page.views.pop()
        if not self.page.views:
            self.page.go("/login")
        else:
            top_view = self.page.views[-1]
            self.page.go(top_view.route)

def main_app(page: ft.Page):
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    NoteSharingApp(page)

def main(page: ft.Page):
    ft.app(target=main_app, view=ft.AppView.WEB_BROWSER)

if __name__ == "__main__":
    main(None)
