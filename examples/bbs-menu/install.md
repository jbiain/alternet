# Installing Alternet

Fastest way in, after installing:

    alternet start       # sets up, joins the network, opens this BBS
    alternet tour        # a one-minute demo of what makes it different

Needs Python 3.9+.

    pip install -e core/            # from the project source, installs `alternet` and Reticulum
    alternet init --no-auto --standalone
    alternet publish <directory> --name <name>
    alternet node                   # announce and serve while this runs

On a phone without a package manager (tested with a-Shell on iOS):

    pip install --no-deps rns
    python -m alternet init --no-auto --standalone
    python -m alternet connect <host>:4242
    python -m alternet read <site-id> --wait 20

To join the public relay so you're reachable across networks:

    alternet connect y-0-x.com:4242
