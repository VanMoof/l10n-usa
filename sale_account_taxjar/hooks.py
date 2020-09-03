# © 2019 Vanmoof B.V. (<https://vanmoof.com>)#
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging
from odoo import api, SUPERUSER_ID
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


def post_init_hook(cr, pool):
    env = api.Environment(cr, SUPERUSER_ID, {})
    error_count = 0
    tax_cls = env['account.tax']
    invoices = env['account.invoice'].search([('company_id', '=', 4)])

    # clone invoice.amount_tax into a backup column
    env.cr.execute("""
    ALTER TABLE account_invoice
    ADD COLUMN amount_tax_pre_taxjar_mig Numeric;
    UPDATE account_invoice SET amount_tax_pre_taxjar_mig = amount_tax;
    """)

    for inv in invoices:
        b4_amount_total = inv.amount_total
        b4_amount_tax = inv.amount_tax
        b4_amount_untaxed = inv.amount_untaxed
        _logger.info(
            'Invoice B amount_total: {}, amount_tax: {}, '
            'amount_untaxed: {}'.format(
                inv.amount_total, inv.amount_tax, inv.amount_untaxed))

        for line in inv.invoice_line_ids:
            if not line.tax_amt:
                continue
            percent = line.price_subtotal / line.tax_amt * 100
            tax_percent = float_round(
                percent, precision_digits=2, precision_rounding=None,
                rounding_method='HALF-UP')

            tax_name = 'taxjar_{}'.format(tax_percent)
            tax_id = tax_cls.search([('name', '=', tax_name),
                                     ('amount', '=', tax_percent)])
            if not tax_id:
                tax_id = tax_cls.create({
                    'name': tax_name,
                    'amount': tax_percent,
                    'company_id': 4,
                    'type': 'percent',
                })
            line.write({
                'invoice_line_tax_ids': [(6, 0, [tax_id.id])],
            })

        if not all([b4_amount_total == inv.amount_total,
                    b4_amount_tax == inv.amount_tax,
                    b4_amount_untaxed == inv.amount_untaxed]):
            _logger.error('Not OK')
        else:
            _logger.info('OK')

    _logger.info('--- Summary total error count {} ---'.format(error_count))
