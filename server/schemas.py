from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=512)
    newPassword: str = Field(min_length=12, max_length=512)


class StrategySelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reconnect: bool = True


class DeviceAliasesRequest(BaseModel):
    aliases: dict[str, str] = Field(default_factory=dict)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=512)
    role: str = "viewer"
    allowedDevices: list[str] = Field(default_factory=list, max_length=256)


class UpdateUserRequest(BaseModel):
    password: str | None = Field(default=None, min_length=12, max_length=512)
    role: str | None = None
    allowedDevices: list[str] | None = Field(default=None, max_length=256)


class SubscriptionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=4096)
    interval: int = Field(default=21600, ge=900, le=2_592_000)
    enabled: bool = True


class SubscriptionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    interval: int | None = Field(default=None, ge=900, le=2_592_000)
    enabled: bool | None = None


class NodeRenameRule(BaseModel):
    pattern: str = Field(min_length=1, max_length=240)
    replacement: str = Field(default="", max_length=240)


class SubscriptionFilterRequest(BaseModel):
    includeRegex: str = Field(default="", max_length=240)
    excludeRegex: str = Field(default="", max_length=240)
    excludeKeywords: list[str] = Field(default_factory=list, max_length=64)
    renameRules: list[NodeRenameRule] = Field(default_factory=list, max_length=32)
    source: str = Field(default="manual", pattern="^(manual|ai)$")

    @field_validator("excludeKeywords")
    @classmethod
    def validate_filter_keywords(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 80 for value in normalized):
            raise ValueError("每个排除关键词最多 80 个字符")
        return normalized


class SubscriptionAIAnalyzeRequest(BaseModel):
    instruction: str = Field(default="", max_length=1000)


class AISettingsRequest(BaseModel):
    provider: str = Field(pattern="^(deepseek|openrouter)$")
    model: str = Field(min_length=1, max_length=200)
    apiKey: str | None = Field(default=None, min_length=8, max_length=4096)
    clearApiKey: bool = False


class TrafficAnomalySettingsRequest(BaseModel):
    enabled: bool
    autonomous: bool
    thresholdBytes: int = Field(ge=100 * 1024**2, le=10 * 1024**4)
    actionPolicy: str = Field(pattern="^(ai|block|direct|alert)$")
    cooldownSeconds: int = Field(ge=300, le=7 * 86400)
    protectedTargets: list[str] = Field(default_factory=list, max_length=128)


class RuleSetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=2048)
    policy: str = Field(min_length=1, max_length=300)
    enabled: bool = True
    interval: int = Field(default=86400, ge=300, le=2_592_000)
    behavior: str = Field(default="classical", pattern="^(classical|domain|ipcidr)$")
    format: str = Field(default="text", pattern="^(text|yaml|mrs)$")


class RuleSetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    policy: str | None = Field(default=None, min_length=1, max_length=300)
    enabled: bool | None = None
    interval: int | None = Field(default=None, ge=300, le=2_592_000)
    behavior: str | None = Field(default=None, pattern="^(classical|domain|ipcidr)$")
    format: str | None = Field(default=None, pattern="^(text|yaml|mrs)$")


class RuleMoveRequest(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class CustomRuleRequest(BaseModel):
    content: str = Field(min_length=3, max_length=4096)
    placement: str = Field(default="before", pattern="^(before|after)$")
    note: str = Field(default="", max_length=300)


class CustomRuleUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=3, max_length=4096)
    placement: str | None = Field(default=None, pattern="^(before|after)$")
    note: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


class GitHubSyncRequest(BaseModel):
    repo: str = Field(default="", max_length=200)
    branch: str = Field(default="", max_length=200)
    path: str = Field(default="", max_length=500)
    token: str | None = Field(default=None, min_length=1, max_length=512)
