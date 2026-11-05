# Command reference

    init        create your node and owner key
    publish     publish a directory of .txt/.md pages as a signed site
    sites       list sites in your local store
    ls          list pages of a site
    read        read a page (fetches from the network if needed)
    pin         keep a site replicated and up to date while your node runs
    node        run your node: announce and serve your sites, keep pins updated
    connect     add a peer to connect to (HOST:PORT)
    listen      accept connections on a TCP port
    gateway     serve your public sites to an ordinary web browser (local, read-only)
    export      write a site to an .altbundle file (USB/SD)
    import      verify and import an .altbundle file
    trust       allow a peer (by peer id) to read your private sites
    untrust     remove a peer from your trusted list
    trusted     list trusted peers
    name        local petnames for sites: name add NAME SITE[@ADDR] | rm NAME | list
    address     show your node address (for SITE@ADDRESS references)
    id          show your owner public key

## Fastest ways in
- `alternet start`  - set up, join the network, open the landing BBS (address bar first)
- `alternet tour`   - a one-minute demo: sign, replicate, reject tampering, survive the publisher going offline
- `alternet world`  - walk a first-person 3D view of the network; sites are doors (truecolor terminal)
- `alternet view <png-file | site> [page]` - show a PNG in the terminal

## Apps, forms and storage

- `alternet app-serve` / `alternet open ADDRESS[/APP]`: host or use sandboxed terminal apps (see docs/013-security.md).
- `alternet gc [--limit MB]`: keep your local store under a size limit; pinned and your own sites are never dropped.
- `alternet sites` shows `offline-ok` for sites you hold completely (readable with no network) and `PARTIAL` otherwise.
- Pages can contain images (`![alt](pic.png)`) and forms (`:input`, `:check`, `:calc`); see calc.md on the BBS.
