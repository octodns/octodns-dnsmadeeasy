## DNS Made Easy provider for octoDNS

An [octoDNS](https://github.com/octodns/octodns/) provider that targets [DNS Made Easy](https://dnsmadeeasy.com/).

### Installation

#### Command line

```
pip install octodns-dnsmadeeasy
```

#### requirements.txt/setup.py

Pinning specific versions or SHAs is recommended to avoid unplanned upgrades.

##### Versions

```
# Start with the latest versions and don't just copy what's here
octodns==1.0.0
octodns-dnsmadeeasy==0.0.4
```

##### SHAs

```
# Start with the latest/specific versions and don't just copy what's here
-e git+https://git@github.com/octodns/octodns.git@9da19749e28f68407a1c246dfdf65663cdc1c422#egg=octodns
-e git+https://git@github.com/octodns/octodns-dnsmadeeasy.git@ec9661f8b335241ae4746eea467a8509205e6a30#egg=octodns_dnsmadeeasy
```

### Configuration

```yaml
providers:
  dnsmadeeasy:
    class: octodns_dnsmadeeasy.DnsMadeEasyProvider
    # Your DnsMadeEasy api key (required)
    api_key: env/DNSMADEEASY_API_KEY
    # Your DnsMadeEasy secret key (required)
    secret_key: env/DNSMADEEASY_SECRET_KEY
    # Whether or not to use Sandbox environment
    # (optional, default is false)
    #sandbox: true
    # The maximum number of records to submit in one request to the DnsMadeEasy API
    # (optional, default is 200)
    #batch_size: 100
```

### Support Information

#### Records

DnsMadeEasyProvider supports A, AAAA, ALIAS (ANAME), CAA, CNAME, MX, NS, PTR, SPF, SRV, and TXT. There are some restrictions on CAA tags.

#### Dynamic

DnsMadeEasyProvider does not support dynamic records.

### Development

See the [/script/](/script/) directory for some tools to help with the development process. They generally follow the [Script to rule them all](https://github.com/github/scripts-to-rule-them-all) pattern. Most useful is `./script/bootstrap` which will create a venv and install both the runtime and development related requirements. It will also hook up a pre-commit hook that covers most of what's run by CI.
