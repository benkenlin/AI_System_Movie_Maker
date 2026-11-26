from pathlib import Path
from ai_content.providers import ProviderConfig, CloudflareImageProvider

config = ProviderConfig.from_env()

print("Account ID configured:", bool(config.cloudflare_account_id))
print("API token configured:", bool(config.cloudflare_token))
print("Image model:", config.cloudflare_image_model)

output = Path("outputs/provider_test/cloudflare_test.png")

CloudflareImageProvider(config).generate(
    "A traditional Ethiopian coffee ceremony in a beautiful home, "
    "cinematic documentary photography, natural light",
    output,
    width=1024,
    height=768
)

print("SUCCESS: Cloudflare generated:", output.resolve())