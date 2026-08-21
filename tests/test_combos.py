import json
import tempfile
import unittest
from pathlib import Path

from server.database import connect, migrate
from server.main import ComboStore, NodeRegionStore


def _user(user_id: int, role: str) -> dict:
    return {"id": user_id, "role": role}


def _payload(name: str, strategy: str = "region_sticky") -> dict:
    return {
        "name": name,
        "subscriptionIds": [],
        "strategy": strategy,
        "rotateIntervalSeconds": 1800,
        "crossRegionIntervalSeconds": 259200,
        "enabled": True,
    }


class ComboStoreTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._directory.name)
        self.database = self.data_dir / "egresscope.db"
        with connect(self.database) as connection:
            migrate(connection)
            connection.executemany(
                "INSERT INTO users(id,username,password_hash,role,allowed_devices,created_at) VALUES(?,?,?,?,?,?)",
                [
                    (1, "alice", "x", "viewer", "[]", 0),
                    (2, "bob", "x", "viewer", "[]", 0),
                    (3, "root", "x", "admin", "[]", 0),
                ],
            )
            connection.executemany(
                """
                INSERT INTO subscriptions(id,owner_id,name,url,interval_seconds,enabled,gateway_enabled,payload_json,raw_payload_json,usage_json,delivery_token,node_count,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    ("sub-a", 1, "A", "https://a.example", 3600, 1, 0,
                     json.dumps([{"name": "🇺🇸 洛杉矶 01", "type": "ss", "server": "1.1.1.1", "port": 443}]), "[]", "{}", "ta", 1, 0, 0),
                    ("sub-b", 2, "B", "https://b.example", 3600, 1, 0,
                     json.dumps([{"name": "🇯🇵 东京 01", "type": "ss", "server": "2.2.2.2", "port": 443}]), "[]", "{}", "tb", 1, 0, 0),
                ],
            )
        self.store = ComboStore(lambda: connect(self.database), NodeRegionStore(lambda: connect(self.database)))

    def tearDown(self):
        self._directory.cleanup()

    def test_viewer_can_create_combo_from_own_subscriptions(self):
        combo = self.store.create(_user(1, "viewer"), {**_payload("我的组合"), "subscriptionIds": ["sub-a"]})
        self.assertEqual(combo["ownerId"], 1)
        self.assertEqual([item["name"] for item in self.store.pool(combo["id"])], ["🇺🇸 洛杉矶 01"])
        self.assertTrue(combo["deliveryPaths"]["clash"].startswith("/sub/combo/"))
        self.assertTrue(combo["deliveryPaths"]["surge"].endswith("/surge.conf"))

    def test_viewer_cannot_include_another_users_subscription(self):
        with self.assertRaises(ValueError):
            self.store.create(_user(1, "viewer"), {**_payload("越权"), "subscriptionIds": ["sub-b"]})

    def test_viewer_cannot_modify_or_delete_another_users_combo(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("管理组合"), "subscriptionIds": ["sub-a", "sub-b"]})
        with self.assertRaises(KeyError):
            self.store.update(combo["id"], _user(2, "viewer"), {"name": "劫持"})
        with self.assertRaises(KeyError):
            self.store.delete(combo["id"], _user(2, "viewer"))
        with self.assertRaises(KeyError):
            self.store.rotate_delivery_token(combo["id"], _user(2, "viewer"))

    def test_viewer_list_only_contains_own_combos_and_pool_is_owner_scoped(self):
        self.store.create(_user(1, "viewer"), {**_payload("爱丽丝组合"), "subscriptionIds": ["sub-a"]})
        self.store.create(_user(2, "viewer"), {**_payload("鲍勃组合"), "subscriptionIds": ["sub-b"]})
        own = self.store.list(_user(1, "viewer"))
        self.assertEqual([item["name"] for item in own], ["爱丽丝组合"])
        admin_view = self.store.list(_user(3, "admin"))
        self.assertEqual(len(admin_view), 2)
        alice_combo = self.store.list(_user(1, "viewer"))[0]
        pool = self.store.pool(alice_combo["id"])
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool[0]["name"], "🇺🇸 洛杉矶 01")
        self.assertEqual(pool[0]["subscriptionId"], "sub-a")
        self.assertEqual(pool[0]["nodeKey"], "sub-a::🇺🇸 洛杉矶 01")

    def test_delivery_generates_merged_profile_for_owner(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("合并"), "subscriptionIds": ["sub-a", "sub-b"]})
        clash = self.store.delivery(combo["deliveryPaths"]["clash"].split("/")[-2], "clash")
        self.assertIn("🇺🇸 A 美国-洛杉矶", clash)
        self.assertIn("🇯🇵 B 日本-东京", clash)
        self.assertIn("proxies:", clash)

    def test_delivery_remains_available_when_rotation_is_disabled(self):
        combo = self.store.create(_user(1, "viewer"), {**_payload("暂停轮换"), "subscriptionIds": ["sub-a"]})
        self.store.update(combo["id"], _user(1, "viewer"), {"enabled": False})
        token = combo["deliveryPaths"]["clash"].split("/")[-2]
        clash = self.store.delivery(token, "clash")
        self.assertIn("🇺🇸 A 美国-洛杉矶", clash)
        self.assertIn("proxies:", clash)

    def test_canonical_names_use_exit_country_city_format(self):
        # 给第二个订阅注入与 sub-a 同名的节点，验证 “<emoji> <Provider> <Country>-<City>” 格式。
        with connect(self.database) as connection:
            connection.execute(
                "UPDATE subscriptions SET payload_json = ? WHERE id = 'sub-b'",
                (json.dumps([{"name": "🇺🇸 洛杉矶 01", "type": "ss", "server": "9.9.9.9", "port": 443}]),),
            )
        combo = self.store.create(_user(3, "admin"), {**_payload("去重"), "subscriptionIds": ["sub-a", "sub-b"]})
        pool = self.store.pool(combo["id"])
        canon = self.store.canonical_names(pool)
        values = [canon[str(node["nodeKey"])] for node in pool]
        self.assertEqual(len(values), 2)
        self.assertEqual(len(set(values)), 2, "同名节点必须生成互不相同的 mihomo 代理名")
        self.assertEqual(sorted(values), ["🇺🇸 A 美国-洛杉矶", "🇺🇸 B 美国-洛杉矶"])

    def test_canonical_names_append_id_for_same_provider_country_city(self):
        # 同一订阅、同一出口国家城市的多节点追加 -1/-2/… 去重后缀。
        with connect(self.database) as connection:
            connection.execute(
                "UPDATE subscriptions SET payload_json = ? WHERE id = 'sub-a'",
                (json.dumps([
                    {"name": "🇺🇸 洛杉矶 01", "type": "ss", "server": "1.1.1.1", "port": 443},
                    {"name": "🇺🇸 洛杉矶 02", "type": "ss", "server": "2.2.2.2", "port": 443},
                ]),),
            )
        combo = self.store.create(_user(3, "admin"), {**_payload("去重"), "subscriptionIds": ["sub-a"]})
        pool = self.store.pool(combo["id"])
        canon = self.store.canonical_names(pool)
        self.assertEqual(sorted(canon.values()), ["🇺🇸 A 美国-洛杉矶-1", "🇺🇸 A 美国-洛杉矶-2"])

    def test_canonical_names_use_probed_country_and_city(self):
        # 出口探测（geoip）写入的国家+城市优先于名称启发式。
        combo = self.store.create(_user(3, "admin"), {**_payload("出口"), "subscriptionIds": ["sub-a"]})
        self.store._regions.set_geoip("sub-a", "🇺🇸 洛杉矶 01", "香港", "香港", "154.92.130.35")
        pool = self.store.pool(combo["id"])
        canon = self.store.canonical_names(pool)
        self.assertEqual(list(canon.values()), ["🇭🇰 A 香港"])

    def test_canonical_names_collapse_default_city(self):
        # 离线库对部分机房 IP 只有国家级数据（region=默认），命名应省略“默认”段。
        combo = self.store.create(_user(3, "admin"), {**_payload("默认城市"), "subscriptionIds": ["sub-a"]})
        self.store._regions.set_geoip("sub-a", "🇺🇸 洛杉矶 01", "香港", "默认", "154.92.130.35")
        pool = self.store.pool(combo["id"])
        canon = self.store.canonical_names(pool)
        self.assertEqual(list(canon.values()), ["🇭🇰 A 香港"])

    def test_set_geoip_collapses_city_state_districts(self):
        # 城邦（香港/新加坡）的出口城市即城邦本身，区划（Kowloon/葵涌）归一化为城邦。
        self.store._regions.set_geoip("sub-a", "🇭🇰 香港 01", "香港", "Kowloon", "1.2.3.4")
        self.assertEqual(self.store._regions.region_of("sub-a", "🇭🇰 香港 01"), "香港")
        self.store._regions.set_geoip("sub-b", "🇸🇬 新加坡 01", "新加坡", "Singapore", "2.3.4.5")
        self.assertEqual(self.store._regions.region_of("sub-b", "🇸🇬 新加坡 01"), "新加坡")

    def test_inject_groups_generates_best_balance_smart_per_country(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("组生成"), "subscriptionIds": ["sub-a", "sub-b"]})
        pool = self.store.pool(combo["id"])
        config = {"proxies": [], "proxy-groups": [{"name": "节点选择", "type": "select", "proxies": ["DIRECT"]}]}
        result = self.store.inject_groups(config, combo, pool)
        names = [str(group.get("name")) for group in result["proxy-groups"]]
        self.assertIn("美国智能", names)
        self.assertIn("美国最佳", names)
        self.assertIn("美国均衡", names)
        self.assertIn("美国", names)
        entry = next(group for group in result["proxy-groups"] if group["name"] == "节点选择")
        self.assertIn("美国", entry["proxies"])
        smart = next(group for group in result["proxy-groups"] if group["name"] == "美国智能")
        self.assertEqual(smart["type"], "select")
        best = next(group for group in result["proxy-groups"] if group["name"] == "美国最佳")
        self.assertEqual(best["type"], "url-test")
        balance = next(group for group in result["proxy-groups"] if group["name"] == "美国均衡")
        self.assertEqual(balance["type"], "load-balance")
        # 安全约束：具体国家组绝不包含 DIRECT。
        country_family = [group for group in result["proxy-groups"] if str(group.get("name")) in ("美国", "美国最佳", "美国均衡", "美国智能")]
        self.assertTrue(country_family)
        for group in country_family:
            self.assertNotIn("DIRECT", [str(item) for item in (group.get("proxies") or [])], f"{group['name']} 不得包含 DIRECT")

    def test_inject_groups_upgrades_existing_flagged_family_in_place(self):
        # 基座配置：国旗前缀家族，其中 “🇺🇸 美国智能” 实为 LoadBalance（误标）。
        combo = self.store.create(_user(3, "admin"), {**_payload("升级"), "subscriptionIds": ["sub-a"]})
        pool = self.store.pool(combo["id"])
        config = {
            "proxies": [],
            "proxy-groups": [
                {"name": "节点选择", "type": "select", "proxies": ["🇺🇸 美国"]},
                {"name": "🇺🇸 美国", "type": "select", "proxies": ["🇺🇸 美国最佳", "🇺🇸 美国智能", "🔧 手动切换"]},
                {"name": "🇺🇸 美国最佳", "type": "url-test", "url": "http://x", "interval": 300, "proxies": ["🇺🇸 洛杉矶 01"]},
                {"name": "🇺🇸 美国智能", "type": "load-balance", "proxies": ["🇺🇸 洛杉矶 01"]},
                {"name": "🔧 手动切换", "type": "select", "proxies": ["🇺🇸 洛杉矶 01"]},
            ],
        }
        result = self.store.inject_groups(config, combo, pool)
        names = {str(group.get("name")): group for group in result["proxy-groups"]}
        # 误标 LoadBalance 改名均衡，补真智能（Selector），不再新建裸名并行家族。
        self.assertIn("🇺🇸 美国均衡", names)
        self.assertEqual(names["🇺🇸 美国均衡"]["type"], "load-balance")
        self.assertEqual(names["🇺🇸 美国智能"]["type"], "select")
        self.assertNotIn("美国", names)
        self.assertNotIn("美国智能", names)
        parent = names["🇺🇸 美国"]
        proxies = [str(item) for item in parent["proxies"]]
        self.assertEqual(proxies[:3], ["🇺🇸 美国最佳", "🇺🇸 美国均衡", "🇺🇸 美国智能"])
        self.assertIn("🔧 手动切换", proxies)
        # 安全约束：具体国家组绝不包含 DIRECT。
        for group_name in ("🇺🇸 美国", "🇺🇸 美国最佳", "🇺🇸 美国均衡", "🇺🇸 美国智能"):
            self.assertNotIn("DIRECT", [str(item) for item in (names[group_name].get("proxies") or [])], f"{group_name} 不得包含 DIRECT")
        # 防环：国家父组不能反向写进“手动切换”（否则形成代理组环，mihomo 拒绝）。
        self.assertNotIn("🇺🇸 美国", [str(item) for item in (names["🔧 手动切换"].get("proxies") or [])])
        # 幂等：再注入一次结构不变。
        again = self.store.inject_groups(result, combo, pool)
        again_names = {str(group.get("name")) for group in again["proxy-groups"]}
        self.assertEqual(again_names, set(names))

    def test_family_groups_resolves_flagged_family(self):
        payload = {
            "proxies": {
                "🇺🇸 美国": {"type": "Selector", "all": []},
                "🇺🇸 美国最佳": {"type": "URLTest", "all": []},
                "🇺🇸 美国均衡": {"type": "LoadBalance", "all": []},
                "🇺🇸 美国智能": {"type": "Selector", "all": []},
            }
        }
        smart, parent = self.store._family_groups(payload, "美国")
        self.assertEqual(smart, "🇺🇸 美国智能")
        self.assertEqual(parent, "🇺🇸 美国")

    def test_inject_probe_adds_probe_group_and_rule_for_gateway_combo(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("探测"), "subscriptionIds": ["sub-a", "sub-b"]})
        self.store.activate(combo["id"])
        config = {
            "proxies": [],
            "proxy-groups": [],
            "rules": ["MATCH,DIRECT"],
        }
        result = self.store.inject_probe(config)
        names = [str(group.get("name")) for group in result["proxy-groups"]]
        self.assertIn("🔍 出口探测", names)
        self.assertTrue(any(str(rule).startswith("DOMAIN-SUFFIX,api.ipify.org,🔍 出口探测") for rule in result["rules"]))
        self.assertEqual(result["rules"][0], "DOMAIN-SUFFIX,api.ipify.org,🔍 出口探测")

    def test_probe_candidates_skip_manual_and_fresh_geoip(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("候选"), "subscriptionIds": ["sub-a"]})
        self.store.activate(combo["id"])
        self.store._regions.set_geoip("sub-a", "🇺🇸 洛杉矶 01", "美国", "洛杉矶", "1.2.3.4")
        self.store._regions.assign_manual("sub-a::🇺🇸 洛杉矶 01", "美国", "西雅图")
        # manual 覆盖：即使 fresh geoip 也不探测。
        self.assertEqual(self.store.probe_candidates(combo["id"]), [])

    def test_rotation_prefs_persist_and_round_trip(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("偏好", "smart"), "subscriptionIds": ["sub-a"],
                                                      "rotationPrefs": ["usage_balance", "region_latency"]})
        self.assertEqual(combo["rotationPrefs"], ["usage_balance", "region_latency"])
        updated = self.store.update(combo["id"], _user(3, "admin"), {"rotationPrefs": ["node_delay", "diversity"]})
        self.assertEqual(updated["rotationPrefs"], ["node_delay", "diversity"])
        cleared = self.store.update(combo["id"], _user(3, "admin"), {"rotationPrefs": []})
        self.assertEqual(cleared["rotationPrefs"], [])

    def test_apply_country_decision_persists_all_countries_not_just_last(self):
        import asyncio

        from server import main as main_module

        async def scenario() -> list[str]:
            combo = self.store.create(_user(3, "admin"), {**_payload("多国"), "subscriptionIds": ["sub-a", "sub-b"]})
            stale = self.store.get(combo["id"])  # 循环外只读一次的快照（旧实现会用这份）

            async def fake_select(_group: str, _name: str) -> None:
                return None

            async def fake_get(_path: str) -> dict:
                return {"connections": []}

            async def fake_close(_ids: list[str]) -> tuple[int, int]:
                return (0, 0)

            original = (main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections)
            main_module.mihomo.select = fake_select
            main_module.mihomo.get = fake_get
            main_module.mihomo.close_connections = fake_close
            try:
                await self.store._apply_country_decision(
                    stale, "美国", {"node": "🇺🇸 洛杉矶 01", "region": "洛杉矶", "crossed": False}, "美国智能", "美国")
                await self.store._apply_country_decision(
                    stale, "日本", {"node": "🇯🇵 东京 01", "region": "东京", "crossed": False}, "日本智能", "日本")
            finally:
                main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections = original
            return sorted(self.store.get(combo["id"])["state"].get("countries", {}).keys())

        self.assertEqual(asyncio.run(scenario()), ["日本", "美国"])

    def test_rotation_closes_only_connections_crossing_changed_country_groups(self):
        import asyncio

        from server import main as main_module

        async def scenario() -> tuple[dict, list[tuple[str, str]], list[str]]:
            combo = self.store.create(_user(3, "admin"), {**_payload("重连"), "subscriptionIds": ["sub-a"]})
            self.store._save_state(combo["id"], {"countries": {"美国": {"region": "洛杉矶", "node": "old-node", "lastRotationAt": 123}}})
            selects: list[tuple[str, str]] = []
            closed_ids: list[str] = []

            async def fake_select(group: str, name: str) -> None:
                selects.append((group, name))

            async def fake_get(path: str) -> dict:
                self.assertEqual(path, "/connections")
                return {
                    "connections": [
                        {"id": "old-us", "chains": ["old-node", "🇺🇸 美国智能", "🇺🇸 美国", "🚀 节点选择"]},
                        {"id": "other-country", "chains": ["jp-node", "🇯🇵 日本智能", "🇯🇵 日本", "🚀 节点选择"]},
                        {"id": "direct", "chains": ["DIRECT"]},
                    ]
                }

            async def fake_close(ids: list[str]) -> tuple[int, int]:
                closed_ids.extend(ids)
                return (len(ids), 0)

            original = (main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections)
            main_module.mihomo.select = fake_select
            main_module.mihomo.get = fake_get
            main_module.mihomo.close_connections = fake_close
            try:
                result = await self.store._apply_country_decision(
                    combo,
                    "美国",
                    {"node": "new-node", "region": "圣何塞", "crossed": True},
                    "🇺🇸 美国智能",
                    "🇺🇸 美国",
                    {"proxies": {"🇺🇸 美国智能": {"now": "old-node"}, "🇺🇸 美国": {"now": "🇺🇸 美国智能"}}},
                )
            finally:
                main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections = original
            return result, selects, closed_ids

        result, selects, closed_ids = asyncio.run(scenario())
        self.assertEqual(selects, [("🇺🇸 美国智能", "new-node"), ("🇺🇸 美国", "🇺🇸 美国智能")])
        self.assertEqual(closed_ids, ["old-us"])
        self.assertEqual(result["closedConnections"], 1)
        self.assertTrue(result["selectionChanged"])

    def test_rotation_does_not_close_connections_when_selector_is_unchanged(self):
        import asyncio

        from server import main as main_module

        async def scenario() -> dict:
            combo = self.store.create(_user(3, "admin"), {**_payload("稳定"), "subscriptionIds": ["sub-a"]})
            self.store._save_state(combo["id"], {"countries": {"美国": {"region": "洛杉矶", "node": "same-node", "lastRotationAt": 123}}})

            async def fake_select(_group: str, _name: str) -> None:
                return None

            async def fail_get(_path: str) -> dict:
                raise AssertionError("unchanged selector must not snapshot connections")

            async def fail_close(_ids: list[str]) -> tuple[int, int]:
                raise AssertionError("unchanged selector must not close connections")

            original = (main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections)
            main_module.mihomo.select = fake_select
            main_module.mihomo.get = fail_get
            main_module.mihomo.close_connections = fail_close
            try:
                return await self.store._apply_country_decision(
                    combo,
                    "美国",
                    {"node": "same-node", "region": "洛杉矶", "crossed": False},
                    "🇺🇸 美国智能",
                    "🇺🇸 美国",
                    {"proxies": {"🇺🇸 美国智能": {"now": "same-node"}, "🇺🇸 美国": {"now": "🇺🇸 美国智能"}}},
                )
            finally:
                main_module.mihomo.select, main_module.mihomo.get, main_module.mihomo.close_connections = original

        result = asyncio.run(scenario())
        self.assertFalse(result["changed"])
        self.assertEqual(result["affectedConnections"], 0)

    def test_combo_requires_at_least_one_subscription(self):
        with self.assertRaises(ValueError):
            self.store.create(_user(1, "viewer"), _payload("空组合"))

    def test_disabling_gateway_combo_clears_gateway_flag(self):
        combo = self.store.create(_user(3, "admin"), {**_payload("网关组合"), "subscriptionIds": ["sub-a"]})
        self.store.activate(combo["id"])
        updated = self.store.update(combo["id"], _user(3, "admin"), {"enabled": False})
        self.assertFalse(updated["enabled"])
        self.assertFalse(updated["gatewayEnabled"])


if __name__ == "__main__":
    unittest.main()
