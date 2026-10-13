"""Where clips come from.

Every source turns its clips into the same shape (a dict per clip, see folder.make_clip), so the rest of
ClipShelf doesn't care which recorder made them:

  gg      SteelSeries GG's own library, with its titles, stars, trims and Game/Chat/Mic levels
  folder  any folder of videos (NVIDIA, AMD, Xbox Game Bar, OBS, Medal...), read with ffprobe
"""
