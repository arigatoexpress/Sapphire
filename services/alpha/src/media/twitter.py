import asyncio
import json
import os
import random
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import tweepy
from loguru import logger

try:  # optional local browser-cookie fallback (no API credits needed)
    import browser_cookie3
except Exception:  # pragma: no cover
    browser_cookie3 = None


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class TwitterClient:
    """
    X/Twitter client for posting and account branding.

    Supports two credential modes:
    1) discrete env vars (`SAPPHIRE_TWITTER_API_KEY`, etc.)
    2) bundled secret blob (`SAPPHIRE_TWITTER_API_TOKEN`) in JSON or key-value text.
    """

    def __init__(self):
        self.enabled = _is_true(os.getenv("SAPPHIRE_MEDIA_TWITTER_ENABLED", "true"))

        self.api_key = os.getenv("SAPPHIRE_TWITTER_API_KEY", "").strip()
        self.api_secret = os.getenv("SAPPHIRE_TWITTER_API_SECRET", "").strip()
        self.access_token = os.getenv("SAPPHIRE_TWITTER_ACCESS_TOKEN", "").strip()
        self.access_secret = os.getenv("SAPPHIRE_TWITTER_ACCESS_SECRET", "").strip()
        self.bearer_token = os.getenv("SAPPHIRE_TWITTER_BEARER_TOKEN", "").strip()

        self._load_from_secret_blob()

        self.v2_client: Optional[tweepy.Client] = None
        self.v1_api: Optional[tweepy.API] = None
        self.ready = False
        self.handle = os.getenv("SAPPHIRE_TWITTER_HANDLE", "").strip()

    def _load_from_secret_blob(self):
        """Populate missing fields from bundled secret blob if available."""
        blob = os.getenv("SAPPHIRE_TWITTER_API_TOKEN", "").strip()
        if not blob:
            return

        parsed = self._parse_credential_blob(blob)
        if not parsed:
            logger.warning("⚠️ SAPPHIRE_TWITTER_API_TOKEN is set but could not be parsed.")
            return

        self.api_key = self.api_key or parsed.get("api_key", "")
        self.api_secret = self.api_secret or parsed.get("api_secret", "")
        self.access_token = self.access_token or parsed.get("access_token", "")
        self.access_secret = self.access_secret or parsed.get("access_secret", "")
        self.bearer_token = self.bearer_token or parsed.get("bearer_token", "")

    def _parse_credential_blob(self, blob: str) -> Dict[str, str]:
        """Parse JSON or loose key-value credential blob."""
        out: Dict[str, str] = {}
        def normalize_key(raw: str) -> str:
            return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")

        # JSON first
        if blob.startswith("{"):
            try:
                obj = json.loads(blob)
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if value is None:
                            continue
                        out[normalize_key(key)] = str(value).strip()
            except json.JSONDecodeError:
                pass

        # fallback parse from line-based entries
        if not out:
            for part in re.split(r"[\n\r,]+", blob):
                line = part.strip()
                if not line:
                    continue
                if line.lower().startswith("ck "):
                    out["consumer_key"] = line[3:].strip()
                    continue
                if line.lower().startswith("sk "):
                    out["consumer_secret"] = line[3:].strip()
                    continue
                if line.lower().startswith("bear "):
                    out["bearer_token"] = line[5:].strip()
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                elif ":" in line:
                    k, v = line.split(":", 1)
                else:
                    continue
                out[normalize_key(k)] = v.strip()

        mapped: Dict[str, str] = {}
        aliases = {
            "api_key": ["api_key", "consumer_key", "twitter_api_key", "ck", "x_consumer_key"],
            "api_secret": ["api_secret", "consumer_secret", "twitter_api_secret", "sk", "x_consumer_secret"],
            "access_token": ["access_token", "twitter_access_token", "oauth_token", "token"],
            "access_secret": ["access_secret", "access_token_secret", "twitter_access_secret", "oauth_token_secret", "token_secret"],
            "bearer_token": ["bearer_token", "bear", "twitter_bearer_token"],
        }
        for target, keys in aliases.items():
            for key in keys:
                value = out.get(key)
                if value:
                    mapped[target] = value
                    break
        return mapped

    @staticmethod
    def _is_read_only_error(exc: Exception) -> bool:
        msg = str(exc or "").lower()
        markers = (
            "read-only application cannot post",
            "not configured with the appropriate oauth1 app permissions",
            "oauth1 app permissions",
            "403 forbidden",
        )
        return any(m in msg for m in markers)

    @staticmethod
    def _read_write_fix_hint() -> str:
        return (
            "x_app_read_only: set app permissions to 'Read and write' in X Developer Portal "
            "(User authentication settings), then regenerate Access Token + Access Token Secret "
            "for this app and retry."
        )

    @staticmethod
    def _web_bearer_token() -> str:
        # Public web bearer used by X web app for internal timeline queries.
        return (
            "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
            "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
        )

    async def start(self):
        """Initialize Tweepy clients (v2 for posts, v1 for profile updates)."""
        if not self.enabled:
            logger.info("🚫 Twitter automation disabled via config.")
            return

        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            logger.warning("⚠️ Twitter API credentials missing. Twitter automation unavailable.")
            return

        try:
            self.v2_client = tweepy.Client(
                bearer_token=self.bearer_token or None,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_secret,
                wait_on_rate_limit=True,
            )

            auth = tweepy.OAuth1UserHandler(
                self.api_key,
                self.api_secret,
                self.access_token,
                self.access_secret,
            )
            self.v1_api = tweepy.API(auth, wait_on_rate_limit=True)

            me = await asyncio.to_thread(self.v1_api.verify_credentials)
            if me and getattr(me, "screen_name", None):
                self.handle = self.handle or str(me.screen_name)

            self.ready = True
            logger.info(f"✅ TwitterClient initialized. Handle: @{self.handle or 'unknown'}")
        except Exception as exc:
            self.ready = False
            logger.error(f"❌ Failed to initialize TwitterClient: {exc}")

    async def post(self, text: str) -> Optional[str]:
        """Post a tweet/thread using v2 API."""
        if not self.ready or not self.v2_client:
            raise RuntimeError("TwitterClient not ready")

        tweets = self._split_thread(text)
        return await asyncio.to_thread(self._post_thread_sync, tweets)

    async def update_branding(
        self,
        *,
        name: str = "",
        description: str = "",
        url: str = "",
        location: str = "",
        clear_location: bool = False,
        banner_path: str = "",
        profile_image_path: str = "",
    ) -> Dict[str, Any]:
        """
        Update profile metadata and visual branding via v1 endpoints.
        """
        if not self.ready or not self.v1_api:
            raise RuntimeError("TwitterClient not ready")

        return await asyncio.to_thread(
            self._update_branding_sync,
            name,
            description,
            url,
            location,
            clear_location,
            banner_path,
            profile_image_path,
        )

    async def prune_following(
        self,
        *,
        max_scan: int = 400,
        max_actions: int = 15,
        min_score: int = 2,
        delay_seconds: float = 12.0,
        dry_run: bool = True,
        keep_handles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Conservative quality-prune for following list.

        Safety defaults:
        - scans a bounded window (`max_scan`)
        - performs a small batch (`max_actions`)
        - sleeps between unfollows (`delay_seconds` + jitter)
        - dry-run by default
        """
        if not self.ready or not self.v1_api:
            raise RuntimeError("TwitterClient not ready")

        keep_handles = [h.strip().lstrip("@").lower() for h in (keep_handles or []) if h.strip()]
        return await asyncio.to_thread(
            self._prune_following_sync,
            max_scan,
            max_actions,
            min_score,
            delay_seconds,
            dry_run,
            keep_handles,
        )

    async def unfollow_handles(
        self,
        *,
        handles: List[str],
        max_actions: int = 15,
        delay_seconds: float = 12.0,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        if not self.ready or not self.v1_api:
            raise RuntimeError("TwitterClient not ready")
        normalized = [h.strip().lstrip("@") for h in handles if h and h.strip()]
        return await asyncio.to_thread(
            self._unfollow_handles_sync,
            normalized,
            max_actions,
            delay_seconds,
            dry_run,
        )

    def _post_thread_sync(self, tweets: List[str]) -> str:
        assert self.v2_client is not None

        first_id = None
        previous_id = None
        for i, tweet_text in enumerate(tweets):
            try:
                response = self.v2_client.create_tweet(
                    text=tweet_text,
                    in_reply_to_tweet_id=previous_id,
                )
            except Exception as exc:
                if self._is_read_only_error(exc):
                    raise RuntimeError(self._read_write_fix_hint()) from exc
                raise
            if not response or not response.data:
                raise RuntimeError("Empty response from X API")
            tweet_id = response.data["id"]
            if i == 0:
                first_id = tweet_id
            previous_id = tweet_id
            logger.info(f"🐦 Tweet posted: {tweet_id}")
        return str(first_id)

    def _update_branding_sync(
        self,
        name: str,
        description: str,
        url: str,
        location: str,
        clear_location: bool,
        banner_path: str,
        profile_image_path: str,
    ) -> Dict[str, Any]:
        assert self.v1_api is not None

        result: Dict[str, Any] = {
            "ok": True,
            "updated_profile": False,
            "updated_banner": False,
            "updated_profile_image": False,
            "errors": [],
            "handle": self.handle or "",
        }

        profile_args = {}
        if name.strip():
            profile_args["name"] = name.strip()
        if description.strip():
            profile_args["description"] = description.strip()
        if url.strip():
            profile_args["url"] = url.strip()
        if clear_location:
            profile_args["location"] = ""
        elif location.strip():
            profile_args["location"] = location.strip()

        if profile_args:
            try:
                user = self.v1_api.update_profile(**profile_args)
                result["updated_profile"] = True
                if user and getattr(user, "screen_name", None):
                    self.handle = str(user.screen_name)
                    result["handle"] = self.handle
            except Exception as exc:
                result["ok"] = False
                error = f"update_profile_failed: {exc}"
                if self._is_read_only_error(exc):
                    error = f"{error} | {self._read_write_fix_hint()}"
                result["errors"].append(error)

        if banner_path.strip():
            try:
                banner_file = Path(banner_path).expanduser()
                if not banner_file.exists():
                    raise FileNotFoundError(f"banner_not_found:{banner_file}")
                self.v1_api.update_profile_banner(filename=str(banner_file))
                result["updated_banner"] = True
            except Exception as exc:
                result["ok"] = False
                error = f"update_banner_failed: {exc}"
                if self._is_read_only_error(exc):
                    error = f"{error} | {self._read_write_fix_hint()}"
                result["errors"].append(error)

        if profile_image_path.strip():
            try:
                profile_file = Path(profile_image_path).expanduser()
                if not profile_file.exists():
                    raise FileNotFoundError(f"profile_not_found:{profile_file}")
                self.v1_api.update_profile_image(filename=str(profile_file))
                result["updated_profile_image"] = True
            except Exception as exc:
                result["ok"] = False
                error = f"update_profile_image_failed: {exc}"
                if self._is_read_only_error(exc):
                    error = f"{error} | {self._read_write_fix_hint()}"
                result["errors"].append(error)

        return result

    def _prune_following_sync(
        self,
        max_scan: int,
        max_actions: int,
        min_score: int,
        delay_seconds: float,
        dry_run: bool,
        keep_handles: List[str],
    ) -> Dict[str, Any]:
        assert self.v1_api is not None

        users = []
        using_fallback = False
        try:
            for user in tweepy.Cursor(
                self.v1_api.get_friends,
                count=200,
                skip_status=True,
                include_user_entities=False,
            ).items(max_scan):
                users.append(user)
        except Exception as exc:
            msg = str(exc or "").lower()
            if "limited v1.1 endpoints" in msg or "403 forbidden" in msg:
                users = self._fetch_following_via_web_session(max_scan=max_scan)
                using_fallback = True
            else:
                raise RuntimeError(f"list_following_failed: {exc}") from exc

        candidates: List[Dict[str, Any]] = []
        for user in users:
            screen_name = str(self._field(user, "screen_name", "") or "")
            handle_norm = screen_name.lower()
            if handle_norm in keep_handles:
                continue
            score, reasons = self._signal_score(user)
            if score < min_score:
                candidates.append(
                    {
                        "id": str(self._field(user, "id_str", "") or self._field(user, "id", "")),
                        "screen_name": screen_name,
                        "name": str(self._field(user, "name", "") or ""),
                        "score": score,
                        "reasons": reasons,
                        "followers": int(self._field(user, "followers_count", 0) or 0),
                        "friends": int(self._field(user, "friends_count", 0) or 0),
                    }
                )

        candidates.sort(key=lambda x: (x["score"], x["followers"]))
        planned = candidates[: max(0, max_actions)]

        result: Dict[str, Any] = {
            "ok": True,
            "dry_run": dry_run,
            "max_scan": max_scan,
            "max_actions": max_actions,
            "min_score": min_score,
            "scanned": len(users),
            "scan_source": "x_web_session_graphql" if using_fallback else "api_v1_friends_list",
            "candidates_total": len(candidates),
            "planned_actions": len(planned),
            "planned": planned,
            "unfollowed": [],
            "errors": [],
        }

        if dry_run:
            return result

        for row in planned:
            try:
                self.v1_api.destroy_friendship(user_id=row["id"])
                result["unfollowed"].append(row)
                sleep_s = max(4.0, float(delay_seconds)) + random.uniform(0.5, 2.5)
                time.sleep(sleep_s)
            except Exception as exc:
                msg = str(exc or "").lower()
                if "limited v1.1 endpoints" in msg or "403 forbidden" in msg:
                    try:
                        self._web_session_unfollow(str(row["screen_name"]))
                        result["unfollowed"].append(row)
                        sleep_s = max(4.0, float(delay_seconds)) + random.uniform(0.5, 2.5)
                        time.sleep(sleep_s)
                        continue
                    except Exception as web_exc:
                        error = f"unfollow_failed @{row['screen_name']}: {web_exc}"
                else:
                    error = f"unfollow_failed @{row['screen_name']}: {exc}"
                    if self._is_read_only_error(exc):
                        error = f"{error} | {self._read_write_fix_hint()}"
                result["errors"].append(error)

        if result["errors"]:
            result["ok"] = False
        return result

    def _signal_score(self, user: Any) -> tuple[int, List[str]]:
        text = " ".join(
            [
                str(self._field(user, "name", "") or ""),
                str(self._field(user, "screen_name", "") or ""),
                str(self._field(user, "description", "") or ""),
            ]
        ).lower()

        high_signal_keywords = [
            "research",
            "quant",
            "market",
            "macro",
            "trading",
            "ai",
            "machine learning",
            "open source",
            "engineering",
            "developer",
            "bitcoin",
            "ethereum",
            "crypto",
            "defi",
        ]
        low_signal_keywords = [
            "giveaway",
            "follow back",
            "dm for",
            "pump",
            "memecoin",
            "airdrop",
            "nft drop",
            "100x",
            "signals vip",
            "paid group",
        ]

        followers = int(self._field(user, "followers_count", 0) or 0)
        friends = int(self._field(user, "friends_count", 0) or 0)
        statuses = int(self._field(user, "statuses_count", 0) or 0)
        verified = bool(self._field(user, "verified", False))
        protected = bool(self._field(user, "protected", False))
        default_profile_image = bool(self._field(user, "default_profile_image", False))

        score = 0
        reasons: List[str] = []

        if verified:
            score += 2
            reasons.append("+verified")
        if followers >= 10000:
            score += 2
            reasons.append("+followers>=10k")
        elif followers >= 2000:
            score += 1
            reasons.append("+followers>=2k")
        if friends > 0 and followers / max(1, friends) >= 1.2:
            score += 1
            reasons.append("+follower_ratio")

        matched_hi = [kw for kw in high_signal_keywords if kw in text]
        if matched_hi:
            boost = min(4, len(set(matched_hi)))
            score += boost
            reasons.append(f"+keywords:{boost}")

        matched_lo = [kw for kw in low_signal_keywords if kw in text]
        if matched_lo:
            penalty = min(6, len(set(matched_lo)) * 2)
            score -= penalty
            reasons.append(f"-noise:{penalty}")

        if default_profile_image:
            score -= 2
            reasons.append("-default_pfp")
        if followers < 100 and friends > 1000:
            score -= 2
            reasons.append("-low_followers_high_following")
        if statuses < 20:
            score -= 1
            reasons.append("-low_activity")
        if protected:
            score -= 1
            reasons.append("-protected")

        return score, reasons

    def _unfollow_handles_sync(
        self,
        handles: List[str],
        max_actions: int,
        delay_seconds: float,
        dry_run: bool,
    ) -> Dict[str, Any]:
        assert self.v1_api is not None

        planned = handles[: max(0, max_actions)]
        result: Dict[str, Any] = {
            "ok": True,
            "dry_run": dry_run,
            "requested": len(handles),
            "planned_actions": len(planned),
            "planned": [f"@{h}" for h in planned],
            "unfollowed": [],
            "errors": [],
        }

        if dry_run:
            return result

        for handle in planned:
            try:
                self.v1_api.destroy_friendship(screen_name=handle)
                result["unfollowed"].append(f"@{handle}")
                sleep_s = max(4.0, float(delay_seconds)) + random.uniform(0.5, 2.5)
                time.sleep(sleep_s)
            except Exception as exc:
                msg = str(exc or "").lower()
                if "limited v1.1 endpoints" in msg or "403 forbidden" in msg:
                    try:
                        self._web_session_unfollow(handle)
                        result["unfollowed"].append(f"@{handle}")
                        sleep_s = max(4.0, float(delay_seconds)) + random.uniform(0.5, 2.5)
                        time.sleep(sleep_s)
                        continue
                    except Exception as web_exc:
                        error = f"unfollow_failed @{handle}: {web_exc}"
                else:
                    error = f"unfollow_failed @{handle}: {exc}"
                    if self._is_read_only_error(exc):
                        error = f"{error} | {self._read_write_fix_hint()}"
                result["errors"].append(error)

        if result["errors"]:
            result["ok"] = False
        return result

    def _field(self, user: Any, field: str, default: Any = None) -> Any:
        if isinstance(user, dict):
            return user.get(field, default)
        return getattr(user, field, default)

    def _fetch_following_via_web_session(self, max_scan: int = 400) -> List[Dict[str, Any]]:
        if browser_cookie3 is None:
            raise RuntimeError("list_following_failed: browser_cookie3_not_installed")

        if not self.handle:
            raise RuntimeError("list_following_failed: missing_handle_for_web_fallback")

        try:
            cookiejar = browser_cookie3.chrome(domain_name=".x.com")
        except Exception as exc:
            raise RuntimeError(f"list_following_failed: browser_cookie_load_failed: {exc}") from exc

        ct0 = ""
        twid = ""
        auth = ""
        for c in cookiejar:
            if c.name == "ct0":
                ct0 = c.value
            elif c.name == "twid":
                twid = c.value
            elif c.name == "auth_token":
                auth = c.value

        if not ct0 or not twid or not auth:
            raise RuntimeError("list_following_failed: missing_required_x_session_cookies")

        twid_decoded = urllib.parse.unquote(twid)
        if "=" in twid_decoded:
            user_id = twid_decoded.split("=", 1)[1].strip()
        else:
            user_id = twid_decoded.strip()
        user_id = re.sub(r"[^0-9]", "", user_id)
        if not user_id:
            raise RuntimeError("list_following_failed: invalid_twid_cookie")

        session, headers = self._create_web_session_and_headers(cookiejar, ct0)

        qid = "NElglO5nnh78FWMvYQuwDw"  # Following
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }

        users: List[Dict[str, Any]] = []
        seen: set[str] = set()
        cursor: Optional[str] = None

        while len(users) < max_scan:
            variables: Dict[str, Any] = {
                "userId": user_id,
                "count": 80,
                "includePromotedContent": False,
            }
            if cursor:
                variables["cursor"] = cursor

            url = (
                f"https://x.com/i/api/graphql/{qid}/Following"
                f"?variables={urllib.parse.quote(json.dumps(variables, separators=(',', ':')))}"
                f"&features={urllib.parse.quote(json.dumps(features, separators=(',', ':')))}"
            )
            resp = session.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"list_following_failed: web_graphql_status_{resp.status_code}")

            payload = resp.json()
            entries = []
            instructions = (
                payload.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )
            for ins in instructions:
                if isinstance(ins, dict) and isinstance(ins.get("entries"), list):
                    entries.extend(ins["entries"])

            next_cursor: Optional[str] = None
            added = 0
            for entry in entries:
                entry_id = str(entry.get("entryId", "") or "")
                content = entry.get("content", {}) or {}

                if entry_id.startswith("cursor-bottom-"):
                    next_cursor = content.get("value") or content.get("itemContent", {}).get("value")

                result = (
                    content.get("itemContent", {})
                    .get("user_results", {})
                    .get("result", {})
                )
                if not isinstance(result, dict) or result.get("__typename") != "User":
                    continue

                core = result.get("core", {}) or {}
                legacy = result.get("legacy", {}) or {}
                screen_name = str(core.get("screen_name", "") or "").strip()
                if not screen_name or screen_name.lower() in seen:
                    continue
                seen.add(screen_name.lower())

                users.append(
                    {
                        "id": str(result.get("rest_id", "") or result.get("id", "")),
                        "id_str": str(result.get("rest_id", "") or result.get("id", "")),
                        "screen_name": screen_name,
                        "name": str(core.get("name", "") or ""),
                        "description": str(legacy.get("description", "") or ""),
                        "followers_count": int(legacy.get("followers_count", 0) or 0),
                        "friends_count": int(legacy.get("friends_count", 0) or 0),
                        "statuses_count": int(legacy.get("statuses_count", 0) or 0),
                        "verified": bool(result.get("is_blue_verified", False)),
                        "protected": bool(legacy.get("protected", False)),
                        "default_profile_image": bool(legacy.get("default_profile_image", False)),
                    }
                )
                added += 1
                if len(users) >= max_scan:
                    break

            if not next_cursor or added == 0:
                break
            cursor = next_cursor
            time.sleep(1.2)

        return users

    def _create_web_session_and_headers(self, cookiejar: Any, ct0: str) -> tuple[requests.Session, Dict[str, str]]:
        session = requests.Session()
        session.cookies.update(cookiejar)
        headers = {
            "authorization": f"Bearer {self._web_bearer_token()}",
            "x-csrf-token": ct0,
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "user-agent": "Mozilla/5.0",
        }
        return session, headers

    def _web_session_unfollow(self, handle: str) -> None:
        if browser_cookie3 is None:
            raise RuntimeError("browser_cookie3_not_installed")
        cookiejar = browser_cookie3.chrome(domain_name=".x.com")
        ct0 = next((c.value for c in cookiejar if c.name == "ct0"), "")
        if not ct0:
            raise RuntimeError("missing_ct0_cookie")

        session, headers = self._create_web_session_and_headers(cookiejar, ct0)
        headers["content-type"] = "application/x-www-form-urlencoded"
        payload = {
            "screen_name": handle,
            "include_profile_interstitial_type": "1",
            "skip_status": "1",
            "include_entities": "false",
        }
        resp = session.post(
            "https://x.com/i/api/1.1/friendships/destroy.json",
            headers=headers,
            data=payload,
            timeout=30,
        )
        if resp.status_code != 200:
            text = resp.text[:300].replace("\n", " ")
            raise RuntimeError(f"web_unfollow_status_{resp.status_code}: {text}")

    def _split_thread(self, text: str, limit: int = 280) -> List[str]:
        """Split long text into thread parts."""
        if len(text) <= limit:
            return [text]

        words = text.split()
        tweets: List[str] = []
        current = ""

        for word in words:
            if len(current) + len(word) + (1 if current else 0) <= limit:
                current += (" " if current else "") + word
            else:
                if current:
                    tweets.append(current)
                current = word

        if current:
            tweets.append(current)
        return tweets
