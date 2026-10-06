"""N04: the shipped catalog itself is valid, its generated view is current and its claims are honest.

Kept apart from test_tool_catalog.py on purpose: that file is the declared acceptance of the catalog tool,
and acceptance cannot depend on the freshness of the evidence it is about to record."""
import unittest
from pathlib import Path

import tool_catalog as tc





class ShippedCatalog(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_the_shipped_catalog_is_valid_and_its_view_is_current(self):
        catalog = tc.load_catalog(self.ROOT)
        self.assertEqual(tc.validate_catalog(catalog, self.ROOT), [])
        self.assertEqual(tc.check_rendered(self.ROOT), [])

    def test_only_demonstrated_tools_claim_more_than_legacy_status(self):
        catalog = tc.load_catalog(self.ROOT)
        for item in catalog['tools']:
            status = tc.status_of(item)
            expected = 'current' if status in ('verified', 'active') else 'not-applicable'
            if status != 'legacy-unverified':
                self.assertEqual(tc.verification(item, self.ROOT)['state'], expected, item['id'])
        migrated = {t['id'] for t in catalog['tools'] if t.get('contract_version')}
        self.assertTrue({'delivery-evidence', 'context', 'continuation', 'tool-catalog'} <= migrated)
        self.assertGreater(len(catalog['tools']) - len(migrated), 10, 'unmigrated tools stay visibly legacy-unverified')


if __name__ == '__main__':
    unittest.main()
