#!/bin/bash
# Kisayol tusuyla sesli-ortagin mikrofon dinlemesini ac/kapat - tarayici panelini
# hic acmaya gerek kalmadan, panelin "buyuk daire" butonuyla aynisini yapar.
curl -s -X POST http://127.0.0.1:5005/degistir > /dev/null
