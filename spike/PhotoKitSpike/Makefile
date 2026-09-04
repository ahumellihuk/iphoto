# Build, sign, and run the sandboxed PhotoKit spike bundle without an Xcode project.
#
#   make            build + sign
#   make run ARGS="--variant A1 --subset paired"   (sample.json must be in the chosen scratch folder)
#   make reset-tcc  forget the Photos permission for this bundle

APP      := build/PhotoKitSpike.app
BIN      := $(APP)/Contents/MacOS/PhotoKitSpike
SOURCES  := $(wildcard Sources/*.swift)
IDENTITY ?= $(shell security find-identity -v -p codesigning 2>/dev/null | grep "Apple Development" | head -1 | awk '{print $$2}')
TARGET   ?= arm64-apple-macos26.0
SDK      := $(shell xcrun --sdk macosx --show-sdk-path)
BUNDLE_ID := com.iphoto.PhotoKitSpike

.PHONY: all run clean reset-tcc check-idle

all: $(BIN)

$(BIN): $(SOURCES) Info.plist PhotoKitSpike.entitlements
	mkdir -p $(APP)/Contents/MacOS
	cp Info.plist $(APP)/Contents/Info.plist
	swiftc -O -swift-version 5 -target $(TARGET) -sdk $(SDK) \
	    -framework Photos -framework AppKit -framework CryptoKit \
	    -o $(BIN) $(SOURCES)
	@echo "signing with $(IDENTITY)"
	codesign --force --sign $(IDENTITY) --entitlements PhotoKitSpike.entitlements --timestamp=none $(APP)
	codesign -d --entitlements - $(APP) 2>&1 | grep -c 'app-sandbox' >/dev/null && echo "sandbox entitlement present"

check-idle:
	@if pgrep -f "iphoto archive" >/dev/null; then echo "refusing: 'iphoto archive' is running"; exit 1; fi

run: $(BIN) check-idle
	@echo "launching via LaunchServices; output goes to <scratch>/results/latest.log"
	open -W -a $(CURDIR)/$(APP) --args $(ARGS)
	@tail -n 40 ../scratch/results/latest.log 2>/dev/null || true

reset-tcc:
	tccutil reset Photos $(BUNDLE_ID)

clean:
	rm -rf build
