# © 2020 Vanmoof B.V. (<https://vanmoof.com>)#
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging
from openupgradelib import openupgrade
from odoo import api, SUPERUSER_ID
from odoo.tools.float_utils import float_compare, float_round

_logger = logging.getLogger(__name__)


def migrate_taxjar_amount_to_taxes(env):
    error_count = 0
    tax_cls = env['account.tax'].with_context(active_test=False)
    env.cr.execute(
        """ SELECT id, tax_amt, invoice_id
        FROM account_invoice_line
        WHERE tax_amt IS NOT NULL AND tax_amt != 0; """)
    rows = env.cr.fetchall()
    tax_amts = dict(row[:2] for row in rows)
    invoice_ids = sorted({row[2] for row in rows})

    def get_log(inv, label, amount_total, amount_tax, amount_untaxed):
        return (
            'Invoice {} ({}) amount_total: {}, amount_tax: {}, '
            'amount_untaxed: {}'.format(
                inv.id, label, amount_total, amount_tax, amount_untaxed))

    # Suppress endless flood of 'Actual recompute of field' messages
    models_logger = logging.getLogger('odoo.models')
    models_logger_level = models_logger.getEffectiveLevel()
    models_logger.setLevel(logging.WARNING)

    total = len(invoice_ids)
    count = 0
    for inv in env['account.invoice'].browse(invoice_ids):
        count += 1
        prefix = 'account.invoice#%s (%s of %s)' % (inv.id, count, total)
        amounts_before = (inv.amount_total, inv.amount_tax, inv.amount_untaxed)
        line_amount = sum(
            tax_amts.get(line.id, 0) for line in inv.invoice_line_ids)

        if line_amount and not inv.amount_tax:
            # Special case with incorrect amounts in Odoo 8.0
            _logger.warn('%s: zero invoice tax amount, skipping' % prefix)
            continue

        # The rounding difference exists in the amounts per line as returned
        # from the Taxjar API calls. TODO: does this affect new invoices
        # in 12.0 (so that a single cent price difference is introduced between
        # some of the Magento orders and the orders in Odoo)?
        rounding_diff = float_round(
            inv.amount_tax - line_amount, precision_digits=2)
        if rounding_diff:
            _logger.info(
                'Rounding difference of %s - %s = %s',
                inv.amount_tax, line_amount, rounding_diff)
        if (float_compare(rounding_diff, 0.02, precision_digits=2) == 1 or
                float_compare(rounding_diff, -0.02, precision_digits=2) == -1):
            inv._message_log(
                'Taxjar migration to Odoo 12.0 skipped because of tax amount '
                'difference between invoice (%4f) and lines (%4f).')
            _logger.warn(
                '%s: rounding difference too large (%s), skipping' % (
                    prefix, rounding_diff))
            continue

        for line in inv.invoice_line_ids:
            tax_amt = tax_amts.get(line.id)
            if not tax_amt:
                continue
            # Get rid of the rounding difference ASAP
            if rounding_diff:
                tax_amt += rounding_diff
                rounding_diff = 0
            if not line.price_subtotal:  # Sigh
                continue
            percent = tax_amt / line.price_subtotal * 100
            tax_percent = float_round(percent, precision_digits=4)

            tax_name = 'taxjar_{:.4f}'.format(tax_percent)
            tax_id = tax_cls.search([('name', '=', tax_name)])
            if not tax_id:
                print('No existing tax found with name %s, creating it' %
                      tax_name)
                tax_id = tax_cls.create({
                    'active': False,
                    'name': tax_name,
                    'amount': tax_percent,
                    'company_id': inv.company_id.id,
                    'amount_type': 'percent',
                })
            line.write({
                'invoice_line_tax_ids': [(6, 0, [tax_id.id])],
            })

        inv.compute_taxes()
        amounts_after = (inv.amount_total, inv.amount_tax, inv.amount_untaxed)
        if amounts_before != amounts_after:
            _logger.error('%s: Not OK' % prefix)
            _logger.error(get_log(inv, 'before', *amounts_before))
            _logger.error(get_log(inv, 'after', *amounts_after))
        else:
            _logger.info('%s: OK' % prefix)

    _logger.info('--- Summary total error count {} ---'.format(error_count))
    models_logger.setLevel(models_logger_level)

    env.cr.rollback()
    raise Exception('Testing, rollback')


def post_init_hook(cr, pool):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if openupgrade.column_exists(cr, 'account_invoice_line', 'tax_amt'):
        migrate_taxjar_amount_to_taxes(env)
