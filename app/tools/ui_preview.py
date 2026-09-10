"""Render deterministic UI review boards without opening a device window."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from robi.banners import Banner
from robi.mascot_state import MascotState
from robi.ui.face import FaceRenderer
from robi.ui.menu_screen import MenuScreen
from robi.ui.qr_screen import QrScreen
from robi.ui.showcase import NavAction, Showcase
from robi.ui.theme import PALETTE
from robi.ui.typography import ui_font


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "ui-redesign"
SIZE = (1920, 1280)

ACTIONS = [
    NavAction("Курси", "courses", "courses"),
    NavAction("Події", "events", "events"),
    NavAction("Гуртки", "clubs", "clubs"),
    NavAction("Магазин", "store", "store"),
    NavAction("Галерея", "gallery", "gallery"),
    NavAction("Відео", "video", "video"),
    NavAction("Оплата", "payment", "payment"),
    NavAction("Анкета", "form", "form"),
    NavAction("Контакти", "contacts", "contacts"),
    NavAction("Допомога", "help", "help"),
]


def _asset() -> pygame.Surface:
    path = ROOT / "assets" / "references" / "robi-reference-3d-anniversary.png"
    return pygame.image.load(path).convert_alpha()


def _save(surface: pygame.Surface, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, OUT / name)


def showcase_board() -> None:
    showcase = Showcase(SIZE)
    face = FaceRenderer(showcase.face_size(), compact=True)
    face.show_handle = True
    face.update(0.4)
    face_surface = pygame.Surface(showcase.face_size(), pygame.SRCALPHA)
    face.draw(face_surface)
    target = pygame.Surface(SIZE)
    banners = [
        Banner(
            1,
            "Новий набір відкрито",
            "Створи першого робота разом з нами",
            image="preview",
        )
    ]
    preview = _asset()
    showcase.draw(target, face_surface, banners, ACTIONS, lambda _: preview)
    _save(target, "showcase.png")


def menu_board() -> None:
    screen = MenuScreen(SIZE)
    target = pygame.Surface(SIZE)
    screen.draw_menu(
        target,
        "Чим можу допомогти?",
        [action.label for action in ACTIONS],
        True,
        [action.icon for action in ACTIONS],
    )
    _save(target, "menu.png")


def card_board() -> None:
    screen = MenuScreen(SIZE)
    target = pygame.Surface(SIZE)
    screen.draw_card(
        target,
        "Робототехніка",
        "Складання й програмування роботів. Діти створюють власні алгоритми руху, працюють із датчиками та бачать результат кожного заняття.",
        "1400 грн / місяць",
        _asset(),
    )
    _save(target, "card.png")


def qr_board() -> None:
    screen = QrScreen(SIZE)
    screen.enter()
    screen.update(0.5)
    target = pygame.Surface(SIZE)
    screen.draw(target, "https://itrobotics.com.ua/courses", "Відкрийте сторінку курсу")
    _save(target, "qr.png")


def states_board() -> None:
    cols, rows = 4, 3
    cell_w, cell_h = SIZE[0] // cols, SIZE[1] // rows
    board = pygame.Surface(SIZE)
    board.fill(PALETTE.canvas)
    label_font = ui_font(22, weight="semibold")
    for index, state in enumerate(MascotState):
        x = (index % cols) * cell_w
        y = (index // cols) * cell_h
        face = FaceRenderer((cell_w, cell_h))
        face.show_handle = False
        face.set_state(state)
        face.update(0.48)
        cell = pygame.Surface((cell_w, cell_h))
        face.draw(cell)
        label = label_font.render(state.value, True, PALETTE.hud)
        pill = pygame.Rect(0, 0, label.get_width() + 28, label.get_height() + 14)
        pill.center = (cell_w // 2, cell_h - 30)
        pygame.draw.rect(cell, PALETTE.surface, pill, border_radius=pill.height // 2)
        cell.blit(label, label.get_rect(center=pill.center))
        board.blit(cell, (x, y))
    _save(board, "states.png")


def face_board() -> None:
    target = pygame.Surface(SIZE)
    face = FaceRenderer(SIZE)
    face.show_handle = False
    face.look_at(0.18, -0.08)
    face.update(0.40)
    face.draw(target)
    _save(target, "face.png")


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        showcase_board()
        menu_board()
        card_board()
        qr_board()
        states_board()
        face_board()
    finally:
        pygame.quit()
    print(OUT)


if __name__ == "__main__":
    main()
