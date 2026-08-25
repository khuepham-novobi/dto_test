"""Odoo 19 adapter — the DataOne migration target.

Only what genuinely differs from adapters/base.py lives here. Every claim
below was verified against D:\\Projects\\odoo-19.0.
"""
from __future__ import annotations

import re

from .base import OdooAdapter

# v19 routes records as /odoo/<path>/<id> (web/controllers/home.py:46
# declares '/odoo' and '/odoo/<path:subpath>'); the legacy #id= hash still
# resolves, so both forms are accepted.
_ID_RES = [re.compile(r"/odoo/[^?#]*?/(\d+)(?:[?#]|$)"),
           re.compile(r"[#&]id=(\d+)")]


class Odoo19Adapter(OdooAdapter):
    version = "19"

    # v19 dropped 'product' from the type selection: product.template.type is
    # [('consu','Goods'), ('service','Service'), ('combo','Combo')]
    # (product/models/product_template.py:54). Storability moved to the
    # boolean is_storable added by stock (stock/models/product.py:829).
    def storable_product_values(self) -> dict:
        return {"type": "consu", "is_storable": True}

    def cancel_order(self, order_id: int) -> None:
        # v19 removed the sale.order.cancel wizard entirely: action_cancel()
        # calls _action_cancel() directly (sale/models/sale_order.py:1325).
        # No context key is needed — the base implementation is correct.
        self.rpc.call("sale.order", "action_cancel", [order_id])

    def sales_list_url(self) -> str:
        # v17+ stable, human-readable action routes.
        return f"{self.env.base_url}/odoo/sales"

    def order_id_from_url(self, url: str) -> int | None:
        for rx in _ID_RES:
            m = rx.search(url)
            if m:
                return int(m.group(1))
        return None

    # -- view introspection ---------------------------------------------
    # ir.ui.view.type is [('list','List'), ...] in v19
    # (base/models/ir_ui_view.py:149) — the <tree> tag and the 'tree' view
    # type are both gone. get_view() (ir_ui_view.py:3138) expects
    # view_type='list'. framework.fg_common.form_arch() routes through this
    # so no test body carries a version branch.
    list_view_type = "list"
    list_tag = "list"

    @property
    def ui(self) -> dict:
        return {
            "login_user": ["input#login", "input[name='login']"],
            "login_password": ["input#password", "input[name='password']"],
            "login_submit": ["button[type='submit']"],
            "login_error": [".alert-danger", "p.alert"],
            "webclient_ready": [".o_main_navbar", ".o_home_menu",
                                "header.o_navbar"],
            "list_view_ready": [".o_list_view", ".o_list_renderer",
                                ".o_content"],
            "list_new": ["button.o_list_button_add", ".o_list_button_add",
                         ".o_control_panel_main_buttons button:has-text('New')"],
            "form_view": [".o_form_view"],
            "partner_input": [
                ".o_field_widget[name='partner_id'] input",
                "div[name='partner_id'] input",
            ],
            "m2o_dropdown_item": [
                ".o-autocomplete--dropdown-menu .o-autocomplete--dropdown-item a",
                ".o-autocomplete--dropdown-menu li a",
                ".ui-autocomplete .ui-menu-item a",
            ],
            "add_line": [
                ".o_field_x2many_list_row_add a:first-child",
                "a:has-text('Add a product')",
            ],
            "line_product_input": [
                ".o_selected_row .o_field_widget[name='product_template_id'] input",
                ".o_selected_row .o_field_widget[name='product_id'] input",
                "tr.o_selected_row td[name='product_template_id'] input",
                "tr.o_selected_row td[name='product_id'] input",
            ],
            "line_qty_input": [
                ".o_selected_row .o_field_widget[name='product_uom_qty'] input",
                "tr.o_selected_row td[name='product_uom_qty'] input",
            ],
            "form_save": ["button.o_form_button_save", ".o_form_button_save",
                          ".o_form_status_indicator button[title*='Save']"],
            "form_saved_proof": [".o_form_saved",
                                 ".o_breadcrumb .o_last_breadcrumb_item",
                                 "button.o_form_button_create"],
            "app_menu_sales": [
                "a.o_app[data-menu-xmlid='sale.sale_menu_root']",
                ".o_navbar_apps_menu",
            ],
        }
