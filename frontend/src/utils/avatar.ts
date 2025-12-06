import type { MeProfile } from '../interfaces';

const DISCORD_CDN = 'https://cdn.discordapp.com';

export const buildIdenticon = (seed: string | undefined | null) => {
  const s = seed || 'anon';
  return `https://api.dicebear.com/7.x/identicon/svg?seed=${encodeURIComponent(s)}`;
};

export const buildDiscordAvatarUrl = (
  userId?: string,
  avatarHash?: string | null,
  discriminator?: string | null
) => {
  if (userId && avatarHash) {
    return `${DISCORD_CDN}/avatars/${userId}/${avatarHash}.png?size=128`;
  }
  if (userId && discriminator) {
    const discNum = Number(discriminator);
    const idx = Number.isFinite(discNum) ? discNum % 5 : 0;
    return `${DISCORD_CDN}/embed/avatars/${idx}.png`;
  }
  return undefined;
};

export const resolveAvatarUrl = (me?: Pick<MeProfile, 'id' | 'nickname' | 'avatar_url' | 'discord_user_id' | 'discord_avatar' | 'discriminator'>) => {
  if (!me) return buildIdenticon('anon');
  if (me.avatar_url) return me.avatar_url;
  const discordUrl = buildDiscordAvatarUrl(me.discord_user_id, me.discord_avatar, me.discriminator);
  if (discordUrl) return discordUrl;
  // Align fallback seed with nickname-first (matches leaderboard display)
  return buildIdenticon(me.nickname || me.id);
};
