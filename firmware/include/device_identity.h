#ifndef DEVICE_IDENTITY_H
#define DEVICE_IDENTITY_H

/* Keep the per-payload command/B2B identity consistent in every translation
 * unit. Public/source-only builds fall back through config.h; provisioned
 * flight builds take CMD_BALLOON_ID from the ignored secrets.h first. */
#if __has_include("secrets.h") && !defined(B2B_RF_DIAG_BUILD)
#include "secrets.h"
#endif
#include "config.h"

#endif /* DEVICE_IDENTITY_H */
