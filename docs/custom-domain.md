# Custom domain

The site works at `https://doomarchy.github.io/tablegenius/`. To serve it from your own
domain, buy the domain from any registrar (Cloudflare Registrar, Namecheap and Porkbun are
cheap and support the records below), then:

1. **DNS records at the registrar.** For an apex domain such as `tablegenius.football`:

   | Type | Name | Value |
   |---|---|---|
   | A | @ | 185.199.108.153 |
   | A | @ | 185.199.109.153 |
   | A | @ | 185.199.110.153 |
   | A | @ | 185.199.111.153 |
   | CNAME | www | doomarchy.github.io |

   For a subdomain such as `tables.example.com`, one CNAME record pointing at
   `doomarchy.github.io` is enough.

2. **Tell GitHub Pages.** Repository → Settings → Pages → Custom domain: enter the domain and
   save, then tick "Enforce HTTPS" once the certificate is issued (a few minutes to an hour).

3. **Tell the site.** Create the file `site/public/CNAME` containing just the domain, for
   example `tablegenius.football`, and push. The workflow sees the file and builds the site
   for the root path instead of `/tablegenius/`. Without this file a custom domain would serve
   the site at the wrong path and every link would 404.

4. Update the base URL in `docs/data-feed.md` and any links you have shared.

Tell Claude the domain and it will do steps 3 and 4 for you; steps 1 and 2 need your
registrar and GitHub logins.
