# Raspberry Pi access

The repository contains the deployment and replay tools, a connection template,
and all derived flight data needed by the sender. Each participant can use their
own Raspberry Pi. No private SSH key or password belongs in the repository.

## Your own Pi

Use Raspberry Pi OS on an aarch64 Pi with SSH enabled, Python 3.11 or later,
`curl`, `tar`, and `rsync`. The ground computer needs SSH, rsync, and Elodin binaries.

Add this entry to **your local** `~/.ssh/config`, replacing the example values:

```sshconfig
Host ingenuity-pi
    HostName raspberrypi.local
    User your-pi-user
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

The host name/IP, SSH username, and your private-key file location are the only
connection settings. The private key stays on your computer. Install your public
key on the Pi using your normal SSH setup, then verify `ssh ingenuity-pi hostname`.

From this repository root, inside `nix develop`:

```sh
export INGENUITY_PI_HOST=ingenuity-pi
./scripts/deploy_pi.sh
# With the ground database already running:
./scripts/pi_replay.sh
```

Deployment creates `~/Ingenuity-HITL` and installs uv only under that directory.
It does not modify another application on the Pi. The sender uses Python's
standard library, no Elodin SDK or GPU. The current runtime installer targets
aarch64; adapt its uv archive URL for a different architecture.

## Data transport

This project documents deployment to the user's own Pi. It does not provide
shared access to the author's machine or a remote-access/VPN setup.
The configured SSH account must permit remote forwarding. Pi localhost port
12250 is reserved for one replay session.

The SSH reverse tunnel maps Pi `127.0.0.1:12250` to the participant's ground
`127.0.0.1:2250`. The database stays bound to localhost. Elodin's asset server
uses ground port 2251. No DB IP or database password needs to be copied onto the Pi.

## Local convenience settings

You may put `export INGENUITY_PI_HOST=your-existing-ssh-alias` in `.env.local`
(ignored by Git) and run `source .env.local` before deployment. Shell environment
variables are explicit; scripts do not execute a repository-provided environment
file automatically.
