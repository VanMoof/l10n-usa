# Copyright 2018-2019 Eficent Business and IT Consulting Services S.L.
#   (http://www.eficent.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import fields, models
import odoo.addons.decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _get_from_addresses(self):
        partner_ids = super()._get_from_addresses()
        from_addresses = self.invoice_line_ids.mapped(
            'sourcing_address_id')
        return from_addresses or partner_ids


class InvoiceLine(models.Model):
    _inherit = 'account.invoice.line'

    tax_amt = fields.Float(
        'TaxJar Amount', digits=dp.get_precision('Account'))
