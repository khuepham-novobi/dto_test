"""Odoo 17 adapter — the DataOne baseline version.

Only what genuinely differs from adapters/base.py lives here. Every claim
below was verified against D:\\Projects\\dataone\\odoo-17.0.
"""
from __future__ import annotations

import re

from .base import OdooAdapter

# v17 routes records through the web-client hash: /web#id=<id>&model=...
_ID_RE = re.compile(r"[#&]id=(\d+)")


class Odoo17Adapter(OdooAdapter):
    version = "17"

    # v17 storable products use type='product': the base product module
    # declares type as [('consu','Consumable'), ('service','Service')]
    # (product/models/product_template.py:56) and stock extends it with
    # selection_add=[('product','Storable Product')]
    # (stock/models/product.py:661). is_storable does not exist yet.
    def storable_product_values(self) -> dict:
        return {"type": "product"}

    def cancel_order(self, order_id: int) -> None:
        # v17 sale.order.action_cancel() opens the sale.order.cancel wizard
        # for any non-draft order (_show_cancel_wizard, sale_order.py:1096).
        # The disable_cancel_warning context key is the flag the method
        # itself checks (line 1102) — same business outcome, no dialog.
        self.rpc.call("sale.order", "action_cancel", [order_id],
                      context={"disable_cancel_warning": True})

    def sales_list_url(self) -> str:
        # v17 has no /odoo/<path> route (web/controllers/home.py declares
        # only '/' and '/web'). Resolve the Sales root menu and action by
        # XML id so the URL is stable across databases.
        menu_id = self.rpc.ref("sale.sale_menu_root")
        action_id = (self.rpc.ref("sale.action_quotations_with_onboarding")
                     or self.rpc.ref("sale.action_orders"))
        base = f"{self.env.base_url}/web#menu_id={menu_id}"
        if action_id:
            base += f"&action={action_id}"
        return base + "&model=sale.order&view_type=list"

    def order_id_from_url(self, url: str) -> int | None:
        m = _ID_RE.search(url)
        return int(m.group(1)) if m else None

    # -- view introspection ---------------------------------------------
    # ir.ui.view.type is [('tree','Tree'), ...] in v17
    # (base/models/ir_ui_view.py:163). get_view() exists (ir_ui_view.py:2613)
    # and expects view_type='tree'. framework.fg_common.form_arch() routes
    # through this so no test body carries a version branch.
    list_view_type = "tree"
    list_tag = "tree"

    @property
    def ui(self) -> dict:
        return {
            "login_user": ["input#login", "input[name='login']"],
            "login_password": ["input#password", "input[name='password']"],
            "login_submit": ["button[type='submit']"],
            "login_error": [".alert-danger", "p.alert"],
            "webclient_ready": [".o_main_navbar", ".o_home_menu",
                                "nav.o_main_navbar"],
            "list_view_ready": [".o_list_view", ".o_list_renderer",
                                ".o_list_table", ".o_content"],
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
