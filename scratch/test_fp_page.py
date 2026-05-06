import flet as ft

def main(page: ft.Page):
    fp = ft.FilePicker()
    try:
        print(f"Page ID: {page.session.session_id}")
        print(f"FP Page set: {fp.page is not None}")
    except Exception as e:
        print(f"Error: {e}")
    page.window.close()

if __name__ == "__main__":
    ft.app(target=main)
