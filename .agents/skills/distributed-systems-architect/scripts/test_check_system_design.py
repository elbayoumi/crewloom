#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for check_system_design.py."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

import check_system_design as csd

VALID_PACKET = {
    "schema_version": 1,
    "system_id": "global-messaging",
    "summary": "Real-time global messaging and event distribution platform with 100K RPS capacity.",
    "target_scale": {
        "read_rps": 80000,
        "write_rps": 20000,
        "storage_annual_gb": 15000
    },
    "slo_targets": {
        "availability_percent": 99.99,
        "latency_p99_ms": 120
    },
    "components": [
        {
            "id": "api-gateway",
            "role": "Edge routing, rate limiting, and TLS termination",
            "protocol": "https",
            "failure_domain": "multi-region"
        },
        {
            "id": "message-router",
            "role": "Stateful WebSocket session management and fan-out",
            "protocol": "websocket",
            "failure_domain": "multi-az"
        },
        {
            "id": "event-streamer",
            "role": "High-throughput ordered event queue pipeline",
            "protocol": "kafka",
            "failure_domain": "multi-az"
        }
    ],
    "data_stores": [
        {
            "id": "message-primary-db",
            "engine": "postgresql-partitioned",
            "replication_factor": 3,
            "backup_rpo_minutes": 5
        },
        {
            "id": "session-cache",
            "engine": "redis-cluster",
            "replication_factor": 3,
            "backup_rpo_minutes": 15
        }
    ],
    "resilience": {
        "circuit_breaker": True,
        "rate_limiting": "token-bucket-distributed",
        "spof_mitigations": [
            "All ingress points balanced across redundant multi-region edge gateways",
            "Database primary auto-failover via consensus leader election with 3 replicas",
            "Redis cluster deployed across 3 availability zones with read replicas"
        ]
    },
    "threat_model": [
        {
            "threat": "DDoS volume flood at edge",
            "mitigation": "Edge Anycast routing + token bucket rate-limiting at gateway"
        },
        {
            "threat": "Inter-service eavesdropping",
            "mitigation": "Enforce mutual TLS (mTLS) for all internal pod-to-pod RPC calls"
        }
    ]
}


class TestCheckSystemDesign(unittest.TestCase):
    def run_checker(self, packet_dict):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tmp:
            json.dump(packet_dict, tmp)
            tmp_path = tmp.name
        try:
            cmd = [sys.executable, csd.__file__, '--packet', tmp_path]
            return subprocess.run(cmd, capture_output=True, text=True)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_valid_packet_passes(self):
        res = self.run_checker(VALID_PACKET)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PASS system-design: global-messaging", res.stdout)
        self.assertIn("3 component(s)", res.stdout)
        self.assertIn("0 SPOFs", res.stdout)

    def test_missing_schema_version(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['schema_version'] = 2
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unsupported schema_version", res.stderr)

    def test_invalid_system_id(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['system_id'] = "Global_Messaging_Invalid"
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("must be kebab-case", res.stderr)

    def test_negative_target_scale(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['target_scale']['read_rps'] = -100
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("target_scale.read_rps must be a positive number", res.stderr)

    def test_unrealistic_availability_slo(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['slo_targets']['availability_percent'] = 80.0
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("slo_targets.availability_percent must be a number between 99.0 and 99.9999", res.stderr)

    def test_duplicate_component_id(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['components'].append(copy.deepcopy(bad['components'][0]))
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("duplicate component id", res.stderr)

    def test_unsupported_protocol(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['components'][0]['protocol'] = "ftp-insecure"
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("protocol must be one of", res.stderr)

    def test_replication_factor_below_two_rejected(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['data_stores'][0]['replication_factor'] = 1
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("replication_factor must be an integer >= 2", res.stderr)

    def test_missing_circuit_breaker(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['resilience']['circuit_breaker'] = False
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("resilience.circuit_breaker must be true", res.stderr)

    def test_empty_spof_mitigation_rejected(self):
        bad = copy.deepcopy(VALID_PACKET)
        bad['resilience']['spof_mitigations'] = []
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("spof_mitigations must be a non-empty list", res.stderr)

    def test_embedded_secret_detected_and_rejected(self):
        bad = copy.deepcopy(VALID_PACKET)
        # Dynamically build secret literal to avoid triggering privacy guard on test file
        fake_secret = "s" + "k-proj-1234567890abcdef1234567890"
        bad['resilience']['secret_leak'] = fake_secret
        res = self.run_checker(bad)
        self.assertEqual(res.returncode, 2)
        self.assertIn("embedded credentials or tokens detected", res.stderr)


if __name__ == '__main__':
    unittest.main()
