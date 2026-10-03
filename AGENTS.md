::ILANG
[TYPE:project-rules][PROJECT:vps-deals][LANG:en-US]

::STATE{@PROJECT,kind:static VPS deals directory,brand:vps-deals}
::STATE{@DATA,source:public official provider pages configured in .ilang/site.ilang}

::BOUNDARY{allow:edit templates parser and deterministic Python build/scraper|scope:project}
::BOUNDARY{never:invent offers prices discount rates expiry dates affiliate commissions|scope:permanent}
::BOUNDARY{never:bypass robots login walls or anti-bot controls|scope:permanent}
::RULE{.ilang/site.ilang is the only provider configuration; scraper.py and build.py must read it}
::RULE{Only verified current prices may enter Offer JSON-LD; omit unknown prices and expired offers}
::RULE{Affiliate URLs stay blank until real program URLs are provided and approved}
::RULE{First distribution channel is the public GitHub repository; do not create X or Facebook accounts}
::RULE{Keep runtime static and deterministic; no paid inference APIs or runtime secrets}
